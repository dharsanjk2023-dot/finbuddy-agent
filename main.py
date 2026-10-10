"""FinBuddy command-line chat.

    python main.py                      # chat as user "me"
    python main.py --user dharsan       # separate data + memory per user
    python main.py --auto-approve       # skip approval prompts (not recommended)
    python main.py --model openai:gpt-4o-mini
"""

import argparse
import os
import sqlite3

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from finbuddy.graph import build_graph
from finbuddy.llm import get_llm

MEMORY_DB = os.getenv("FINBUDDY_MEMORY_DB", "memory.db")  # conversation checkpoints


def text_of(message) -> str:
    """AI message content may be a string or a list of content blocks."""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def ask_approval(request: dict, auto: bool) -> bool:
    print("\n  APPROVAL NEEDED")
    for a in request["actions"]:
        print(f"   - {a['tool']}({a['args']})\n     reason: {a['reason']}")
    if auto:
        print("   (auto-approved)")
        return True
    return input("   Approve? [y/N]: ").strip().lower().startswith("y")


def run_turn(app, config: dict, text: str, auto_approve: bool = False) -> str:
    """Send one user message, handle any approval pauses, return the agent's reply."""
    result = app.invoke({"messages": [HumanMessage(text)]}, config)
    while result.get("__interrupt__"):
        request = result["__interrupt__"][0].value
        approved = ask_approval(request, auto_approve)
        result = app.invoke(Command(resume={"approved": approved}), config)
    return text_of(result["messages"][-1])


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="FinBuddy - personal finance AI agent")
    parser.add_argument("--user", default="me", help="user id (data and chat memory are per user)")
    parser.add_argument("--model", default=None, help='e.g. "anthropic:claude-sonnet-5-5"')
    parser.add_argument("--auto-approve", action="store_true", help="skip human approval prompts")
    args = parser.parse_args()

    conn = sqlite3.connect(MEMORY_DB, check_same_thread=False)
    memory = SqliteSaver(conn)  # persists conversation state between runs
    app = build_graph(get_llm(args.model), args.user, checkpointer=memory)
    config = {"configurable": {"thread_id": f"user-{args.user}"}, "recursion_limit": 30}

    print(f"FinBuddy ready (user: {args.user}). Type 'quit' to exit.")
    print('Try: "I spent 450 on lunch today" or "how much did I spend on food this month?"\n')
    while True:
        try:
            text = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in {"quit", "exit", "q"}:
            break
        if not text:
            continue
        try:
            print(f"\nfinbuddy > {run_turn(app, config, text, args.auto_approve)}\n")
        except Exception as exc:  # keep the chat alive on API/network errors
            print(f"\n[error] {type(exc).__name__}: {exc}\n")
    conn.close()


if __name__ == "__main__":
    main()
