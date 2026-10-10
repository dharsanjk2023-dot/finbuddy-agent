"""Generate the architecture / schema diagram: docs/architecture.png

    python make_diagram.py
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

INK, MUTED = "#1f2937", "#6b7280"
BLUE, GREEN, AMBER, GREY = "#dbeafe", "#dcfce7", "#fef3c7", "#f3f4f6"
EDGE = {BLUE: "#2563eb", GREEN: "#16a34a", AMBER: "#d97706", GREY: "#6b7280"}

fig, ax = plt.subplots(figsize=(13, 7.6))
ax.set_xlim(0, 13)
ax.set_ylim(0, 7.6)
ax.axis("off")


def box(x, y, w, h, title, sub="", fill=GREY):
    ax.add_patch(
        FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                       fc=fill, ec=EDGE[fill], lw=1.6)
    )
    ax.text(x + w / 2, y + h / 2 + (0.14 if sub else 0), title, ha="center", va="center",
            fontsize=11, fontweight="bold", color=INK)
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.2, sub, ha="center", va="center", fontsize=8.5, color=MUTED)


def arrow(p1, p2, label="", rad=0.0, color=INK, dy=0.0, dx=0.0):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=14, lw=1.5,
                                 color=color, connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((p1[0] + p2[0]) / 2 + dx, (p1[1] + p2[1]) / 2 + dy, label, ha="center",
                fontsize=8.5, color=color, bbox=dict(fc="white", ec="none", pad=1.5))


ax.text(6.5, 7.25, "FinBuddy - agent architecture (LangGraph)", ha="center", fontsize=15,
        fontweight="bold", color=INK)
ax.text(6.5, 6.95, "ReAct tool loop + human-in-the-loop approval + persistent memory",
        ha="center", fontsize=10, color=MUTED)

# User
box(0.3, 4.9, 1.9, 1.0, "User", "terminal chat\n(main.py)", GREY)
# Graph nodes
box(3.2, 4.9, 2.2, 1.0, "agent", "LLM decides next step", BLUE)
box(6.5, 4.9, 2.2, 1.0, "review", "HITL gate: interrupt()", AMBER)
box(9.8, 4.9, 2.2, 1.0, "tools", "ToolNode runs calls", GREEN)
# END / outputs
box(3.2, 3.2, 2.2, 0.8, "END", "final answer to user", GREY)

arrow((2.2, 5.4), (3.2, 5.4), "message")
arrow((5.4, 5.4), (6.5, 5.4), "tool calls", dy=0.2)
arrow((8.7, 5.4), (9.8, 5.4), "approved /\nnot risky", dy=0.35)
arrow((4.3, 4.9), (4.3, 4.0), "no tool calls")
ax.text(4.3, 4.45, "", fontsize=8)
arrow((10.9, 5.9), (4.9, 5.9), "tool results -> back to agent", rad=0.28, dy=0.78, color=EDGE[GREEN])
arrow((7.6, 4.9), (5.0, 4.9), "rejected -> agent explains", rad=-0.45, dy=-0.75, color="#b45309", dx=0.0)

# Tools list
ax.add_patch(FancyBboxPatch((8.7, 1.5), 4.0, 2.6, boxstyle="round,pad=0.02,rounding_size=0.12",
                            fc="white", ec=EDGE[GREEN], lw=1.2, ls="--"))
ax.text(10.7, 3.85, "7 tools (scoped to the user)", ha="center", fontsize=10, fontweight="bold", color=INK)
for i, t in enumerate(["add_transaction *", "list_transactions", "spending_summary", "set_budget",
                       "budget_status", "delete_transaction **", "convert_currency"]):
    ax.text(8.95 + (i // 4) * 2.0, 3.45 - (i % 4) * 0.42, "- " + t, fontsize=9, color=INK)
ax.text(10.7, 1.65, "*  approval if amount >= 10,000     ** always needs approval",
        ha="center", fontsize=7.8, color="#b45309")
arrow((10.9, 4.9), (10.7, 4.1), "", color=EDGE[GREEN])

# Storage
box(0.3, 0.5, 3.6, 1.2, "memory.db (SqliteSaver)", "conversation checkpoints per user\n+ pending approvals", AMBER)
box(8.9, 0.05, 3.6, 1.0, "finbuddy.db (SQLite)", "transactions, budgets", GREEN)
arrow((4.3, 3.2), (2.4, 1.7), "persist state", rad=0.0, color="#b45309", dx=-0.55)
arrow((10.7, 1.5), (10.7, 1.05), "", color=EDGE[GREEN])
ax.text(11.25, 1.27, "parameterised SQL", fontsize=8.5, color=EDGE[GREEN], ha="center")

# LLM provider
box(0.3, 2.9, 2.4, 1.0, "LLM provider", "Claude / GPT / Gemini\nvia init_chat_model", GREY)
arrow((3.2, 5.0), (2.0, 3.9), "invoke", rad=0.0)

plt.tight_layout()
os.makedirs("docs", exist_ok=True)
plt.savefig("docs/architecture.png", dpi=170, facecolor="white")
print("saved docs/architecture.png")
