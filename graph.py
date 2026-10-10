"""The FinBuddy agent graph (LangGraph).

        START
          |
          v
     +--------+   tool calls?    +---------+  needs approval?   +-------+
     | agent  | ---------------> | review  | -- no ----------> | tools | --+
     |  (LLM) |                  | (HITL)  |                   +-------+   |
     +--------+ <--------------- +---------+ <- rejected                   |
        ^  |  no tool calls            interrupt() pauses here             |
        |  v                                                               |
        | END                                                              |
        +------------------------------------------------------------------+

* agent  : the LLM decides what to do next (answer, or call one or more tools).
* review : human-in-the-loop gate. Risky tool calls (deletes, large amounts) pause the
           graph with interrupt() until the user approves or rejects.
* tools  : executes the approved tool calls and feeds results back to the agent.
The loop repeats until the agent can answer without calling a tool (ReAct pattern).
"""

from datetime import date
from typing import Annotated, TypedDict

from langchain_core.messages import SystemMessage, ToolMessage, trim_messages
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from .tools import CURRENCY, make_tools, needs_approval

MAX_HISTORY_MESSAGES = 40  # sliding window sent to the LLM

SYSTEM_PROMPT = """You are FinBuddy, a friendly personal-finance assistant for user '{user}'.
Today's date is {today}. Default currency is {currency}.

How to work:
- Use the tools for every fact about the user's money. Never invent transactions or totals.
- To log spending or income, call add_transaction. Resolve relative dates ("yesterday",
  "last Friday") to YYYY-MM-DD using today's date.
- For questions about totals, call spending_summary (use real date ranges, e.g. a month is
  first day to last day). To find a specific entry, call list_transactions first.
- After adding an expense, call budget_status if a budget might be affected and warn the
  user when a category is near or over its limit.
- Deleting a transaction or saving a large amount asks the user to approve; if they reject,
  acknowledge it and do not retry.
- If a request is ambiguous (e.g. missing amount), ask one short question instead of guessing.
- Keep answers short and clear. You give budgeting information, not professional
  financial, tax or investment advice."""


class State(TypedDict):
    messages: Annotated[list, add_messages]


def build_graph(llm, user_id: str, checkpointer: BaseCheckpointSaver | None = None):
    """Build and compile the agent. `llm` is any LangChain chat model that supports tools."""
    tools = make_tools(user_id)
    llm_with_tools = llm.bind_tools(tools)

    def agent(state: State) -> dict:
        system = SystemMessage(
            SYSTEM_PROMPT.format(user=user_id, today=date.today().isoformat(), currency=CURRENCY)
        )
        history = trim_messages(
            state["messages"],
            strategy="last",
            token_counter=len,  # count messages, not tokens
            max_tokens=MAX_HISTORY_MESSAGES,
            start_on="human",
            allow_partial=False,
        )
        return {"messages": [llm_with_tools.invoke([system, *history])]}

    def route_after_agent(state: State) -> str:
        return "review" if getattr(state["messages"][-1], "tool_calls", None) else END

    def review(state: State) -> dict:
        """Pause for human approval if any pending tool call is risky."""
        calls = state["messages"][-1].tool_calls
        risky = [(c, needs_approval(c)) for c in calls]
        risky = [(c, why) for c, why in risky if why]
        if not risky:
            return {}

        # Execution stops here until the caller resumes with Command(resume=...).
        decision = interrupt(
            {
                "type": "approval_request",
                "actions": [
                    {"tool": c["name"], "args": c["args"], "reason": why} for c, why in risky
                ],
            }
        )
        if decision.get("approved"):
            return {}
        # Rejected: every tool call in the AI message needs a ToolMessage reply.
        return {
            "messages": [
                ToolMessage(
                    content="NOT EXECUTED: the user rejected this action. Do not retry it.",
                    tool_call_id=c["id"],
                    name=c["name"],
                )
                for c in calls
            ]
        }

    def route_after_review(state: State) -> str:
        # A ToolMessage at the end means the user rejected -> let the agent respond.
        return "agent" if state["messages"][-1].type == "tool" else "tools"

    graph = StateGraph(State)
    graph.add_node("agent", agent)
    graph.add_node("review", review)
    graph.add_node("tools", ToolNode(tools))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"review": "review", END: END})
    graph.add_conditional_edges("review", route_after_review, {"agent": "agent", "tools": "tools"})
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer)
