"""FinBuddy web chat (Streamlit).

Run locally:   streamlit run app.py
Deploy free:   Streamlit Community Cloud (see README) - put your API key in the app's Secrets.

Each browser session gets its own private user id, so visitors never see each other's data.
"""

import os
import traceback
import uuid

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

load_dotenv()

# On Streamlit Cloud the key lives in "Secrets"; copy it into environment variables.
try:
    for _key in ("GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "LLM_MODEL"):
        if _key in st.secrets:
            os.environ.setdefault(_key, str(st.secrets[_key]))
except Exception:  # no secrets file locally - that's fine, .env is used instead
    pass

from finbuddy.graph import build_graph  # noqa: E402  (after env is ready)
from finbuddy.llm import get_llm  # noqa: E402
from seed_demo_data import seed  # noqa: E402

MAX_USER_MESSAGES = int(os.getenv("FINBUDDY_MAX_MESSAGES", "30"))  # protects the free API quota

EXAMPLES = [
    "I spent 450 on lunch today",
    "How much did I spend on food this month?",
    "Which categories am I over budget in?",
    "Set a 4000 budget for transport",
    "I bought a laptop for 55000",
    "Show my last 5 transactions",
]

st.set_page_config(page_title="FinBuddy", page_icon="💰", layout="centered")


# ---------- helpers ----------
def text_of(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def tools_used(messages) -> list[str]:
    """Names of the tools the agent called while answering the latest user message."""
    last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1)
    names: list[str] = []
    for m in messages[last_human + 1:]:
        if isinstance(m, AIMessage):
            names += [c["name"] for c in m.tool_calls]
    return names


def new_session() -> None:
    uid = "web-" + uuid.uuid4().hex[:8]
    st.session_state.user_id = uid
    st.session_state.chat = []
    st.session_state.pending = None
    st.session_state.sent = 0
    st.session_state.config = {"configurable": {"thread_id": uid}, "recursion_limit": 30}
    st.session_state.app = build_graph(get_llm(), uid, MemorySaver())


def record(result: dict) -> None:
    """Store an agent result: either a pending approval request or the final answer."""
    if result.get("__interrupt__"):
        st.session_state.pending = result["__interrupt__"][0].value
        return
    st.session_state.pending = None
    messages = result["messages"]
    st.session_state.chat.append(
        {"role": "assistant", "text": text_of(messages[-1]), "tools": tools_used(messages)}
    )


def friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if any(w in msg.lower() for w in ("429", "quota", "rate", "resource_exhausted")):
        return "The free AI quota is busy right now. Please wait a minute and try again."
    return f"Sorry, something went wrong ({type(exc).__name__}). Please try again."


def run(call) -> None:
    try:
        with st.spinner("FinBuddy is thinking..."):
            record(call())
    except Exception as exc:
        traceback.print_exc()  # full details go to the server log (Manage app > Logs)
        st.session_state.pending = None
        # Last lines of the traceback, shown in an expander so problems can be diagnosed.
        detail = "".join(traceback.format_exception(exc)[-4:])[-1500:]
        st.session_state.chat.append(
            {"role": "assistant", "text": friendly_error(exc), "tools": [], "detail": detail}
        )


# ---------- start session ----------
if "app" not in st.session_state:
    try:
        new_session()
    except Exception as exc:
        st.error(
            "FinBuddy could not start, most likely because no API key is configured.\n\n"
            "Add GOOGLE_API_KEY (or ANTHROPIC_API_KEY) to your .env file locally, or to the "
            f"app's Secrets when deployed.\n\nDetails: {type(exc).__name__}: {exc}"
        )
        st.stop()

# ---------- sidebar ----------
with st.sidebar:
    st.header("FinBuddy")
    st.caption(
        "An AI agent that tracks spending and budgets. It decides which tools to use, "
        "and asks you before risky actions (deletes, amounts of 10,000 or more)."
    )
    if st.button("Load demo data", use_container_width=True):
        n = seed(st.session_state.user_id)
        st.success(f"Loaded {n} demo transactions and 3 budgets.")
    st.markdown("**Try one of these**")
    for example in EXAMPLES:
        if st.button(example, key=f"ex-{example}", use_container_width=True,
                     disabled=st.session_state.pending is not None):
            st.session_state.queued = example
    st.divider()
    if st.button("New conversation", use_container_width=True):
        for k in ("app", "chat", "pending", "sent", "config", "user_id", "queued"):
            st.session_state.pop(k, None)
        st.rerun()
    st.caption("Demo only - please don't enter real financial details. Not financial advice.")

# ---------- main chat ----------
st.title("💰 FinBuddy")
st.caption("Your personal-finance assistant. Click 'Load demo data' in the sidebar, then ask away.")

# Human-in-the-loop: the agent is paused until you approve or reject.
# Shown at the TOP so the buttons are always visible without scrolling.
if st.session_state.pending:
    with st.container(border=True):
        st.warning("**Approval needed** - the agent paused before doing this:")
        for action in st.session_state.pending["actions"]:
            st.markdown(f"- `{action['tool']}` {action['args']}  \n  *Reason: {action['reason']}*")
        col_ok, col_no = st.columns(2)
        decision = None
        if col_ok.button("✅ Approve", use_container_width=True):
            decision = True
        if col_no.button("❌ Reject", use_container_width=True):
            decision = False
        if decision is not None:
            run(lambda: st.session_state.app.invoke(
                Command(resume={"approved": decision}), st.session_state.config))
            st.rerun()

if not st.session_state.chat:
    st.info("Try: **I spent 450 on lunch today** or **How much did I spend on food this month?**")

for item in st.session_state.chat:
    with st.chat_message(item["role"]):
        st.markdown(item["text"])
        if item.get("tools"):
            st.caption("🔧 Tools used: " + " → ".join(item["tools"]))
        if item.get("detail"):
            with st.expander("Technical details (for debugging)"):
                st.code(item["detail"])

prompt = st.chat_input(
    "Type a message...", disabled=st.session_state.pending is not None
)
prompt = prompt or st.session_state.pop("queued", None)

if prompt and st.session_state.pending is None:
    if st.session_state.sent >= MAX_USER_MESSAGES:
        st.session_state.chat.append({
            "role": "assistant",
            "text": f"Demo limit reached ({MAX_USER_MESSAGES} messages). Click 'New conversation' to start again.",
            "tools": [],
        })
    else:
        st.session_state.sent += 1
        st.session_state.chat.append({"role": "user", "text": prompt})
        run(lambda: st.session_state.app.invoke(
            {"messages": [HumanMessage(prompt)]}, st.session_state.config))
    st.rerun()
