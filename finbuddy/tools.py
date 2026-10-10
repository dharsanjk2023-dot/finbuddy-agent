"""Tools the agent can call. Built per user so every query is scoped to that user."""

import os
from datetime import date
from typing import Literal

from langchain_core.tools import tool

from .db import connect

CURRENCY = os.getenv("FINBUDDY_CURRENCY", "INR")
# Transactions at or above this amount need explicit human approval before being saved.
LARGE_TXN_LIMIT = float(os.getenv("FINBUDDY_LARGE_TXN", "10000"))

# Tools that always require human approval (they destroy data).
ALWAYS_APPROVE = {"delete_transaction"}

# Fixed, approximate rates (units of INR per 1 unit). Demo only - not live data.
RATES_TO_INR = {"INR": 1.0, "USD": 83.0, "EUR": 90.0, "GBP": 105.0, "AED": 22.6, "SGD": 62.0}


def needs_approval(tool_call: dict) -> str | None:
    """Return a human-readable reason if this tool call must be approved, else None."""
    name, args = tool_call["name"], tool_call.get("args", {})
    if name in ALWAYS_APPROVE:
        return f"Deleting transaction #{args.get('transaction_id')} cannot be undone."
    if name == "add_transaction" and float(args.get("amount", 0)) >= LARGE_TXN_LIMIT:
        return f"Large transaction ({args.get('amount')} {CURRENCY} >= {LARGE_TXN_LIMIT:g})."
    return None


def _day(value: str) -> str:
    """Validate a YYYY-MM-DD string; empty means today."""
    return date.fromisoformat(value).isoformat() if value else date.today().isoformat()


def make_tools(user_id: str) -> list:
    """Create the tool list bound to one user."""

    @tool
    def add_transaction(
        amount: float,
        category: str,
        description: str = "",
        kind: Literal["expense", "income"] = "expense",
        date_str: str = "",
    ) -> str:
        """Record an expense or income. amount must be positive. date_str is YYYY-MM-DD
        (leave empty for today). Use short lowercase categories such as food, transport,
        rent, shopping, salary, entertainment, bills, health."""
        if amount <= 0:
            return "Error: amount must be positive."
        try:
            day = _day(date_str)
        except ValueError:
            return "Error: date_str must be YYYY-MM-DD."
        with connect() as c:
            cur = c.execute(
                "INSERT INTO transactions (user_id, date, kind, amount, category, description) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, day, kind, amount, category.strip().lower(), description.strip()),
            )
        return f"Saved #{cur.lastrowid}: {kind} {amount:g} {CURRENCY} on {day} [{category.lower()}] {description}"

    @tool
    def list_transactions(
        start_date: str = "",
        end_date: str = "",
        category: str = "",
        kind: str = "",
        limit: int = 20,
    ) -> str:
        """List individual transactions, newest first. Filter by date range (YYYY-MM-DD),
        category and kind. Use this to find a transaction id or show recent activity."""
        sql, args = "SELECT * FROM transactions WHERE user_id = ?", [user_id]
        if start_date:
            sql, args = sql + " AND date >= ?", args + [start_date]
        if end_date:
            sql, args = sql + " AND date <= ?", args + [end_date]
        if category:
            sql, args = sql + " AND category = ?", args + [category.strip().lower()]
        if kind:
            sql, args = sql + " AND kind = ?", args + [kind]
        sql += " ORDER BY date DESC, id DESC LIMIT ?"
        args.append(max(1, min(limit, 100)))
        with connect() as c:
            rows = c.execute(sql, args).fetchall()
        if not rows:
            return "No matching transactions."
        return "\n".join(
            f"#{r['id']} {r['date']} {r['kind']:<7} {r['amount']:>10.2f} {CURRENCY} "
            f"[{r['category']}] {r['description']}"
            for r in rows
        )

    @tool
    def spending_summary(
        start_date: str = "",
        end_date: str = "",
        group_by: Literal["category", "month", "day"] = "category",
        kind: Literal["expense", "income"] = "expense",
    ) -> str:
        """Total money by category, month or day over a date range (YYYY-MM-DD, both
        optional). Use for questions like 'how much did I spend on food in September'."""
        group_sql = {
            "category": "category",
            "month": "substr(date, 1, 7)",
            "day": "date",
        }[group_by]
        sql = (
            f"SELECT {group_sql} AS grp, ROUND(SUM(amount), 2) AS total, COUNT(*) AS n "
            "FROM transactions WHERE user_id = ? AND kind = ?"
        )
        args = [user_id, kind]
        if start_date:
            sql, args = sql + " AND date >= ?", args + [start_date]
        if end_date:
            sql, args = sql + " AND date <= ?", args + [end_date]
        sql += " GROUP BY grp ORDER BY total DESC" if group_by == "category" else " GROUP BY grp ORDER BY grp"
        with connect() as c:
            rows = c.execute(sql, args).fetchall()
        if not rows:
            return "No data for that range."
        grand = sum(r["total"] for r in rows)
        lines = [f"{r['grp']}: {r['total']:.2f} {CURRENCY} ({r['n']} txns)" for r in rows]
        return "\n".join(lines) + f"\nTOTAL {kind}: {grand:.2f} {CURRENCY}"

    @tool
    def set_budget(category: str, monthly_limit: float) -> str:
        """Set or update the monthly budget limit for a category."""
        if monthly_limit <= 0:
            return "Error: monthly_limit must be positive."
        with connect() as c:
            c.execute(
                "INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
                (user_id, category.strip().lower(), monthly_limit),
            )
        return f"Budget set: {category.lower()} = {monthly_limit:g} {CURRENCY}/month"

    @tool
    def budget_status(month: str = "") -> str:
        """Compare spending to budgets for a month (YYYY-MM, empty = current month).
        Reports spent, remaining and any category that is over budget."""
        month = month or date.today().strftime("%Y-%m")
        with connect() as c:
            budgets = c.execute(
                "SELECT category, monthly_limit FROM budgets WHERE user_id = ?", (user_id,)
            ).fetchall()
            spent = {
                r["category"]: r["t"]
                for r in c.execute(
                    "SELECT category, SUM(amount) AS t FROM transactions "
                    "WHERE user_id = ? AND kind = 'expense' AND substr(date, 1, 7) = ? GROUP BY category",
                    (user_id, month),
                )
            }
        if not budgets:
            return "No budgets set yet."
        lines = []
        for b in budgets:
            s, lim = spent.get(b["category"], 0.0), b["monthly_limit"]
            flag = "OVER BUDGET" if s > lim else ("near limit" if s >= 0.8 * lim else "ok")
            lines.append(
                f"{b['category']}: spent {s:.2f} / {lim:.2f} {CURRENCY} "
                f"({s / lim:.0%}, remaining {lim - s:.2f}) -> {flag}"
            )
        return f"Budget status for {month}:\n" + "\n".join(lines)

    @tool
    def delete_transaction(transaction_id: int) -> str:
        """Permanently delete one transaction by id (find the id with list_transactions).
        The user is asked to approve this before it runs."""
        with connect() as c:
            cur = c.execute(
                "DELETE FROM transactions WHERE id = ? AND user_id = ?", (transaction_id, user_id)
            )
        return f"Deleted #{transaction_id}." if cur.rowcount else f"No transaction #{transaction_id} found."

    @tool
    def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
        """Convert between INR, USD, EUR, GBP, AED, SGD using fixed approximate rates."""
        f, t = from_currency.upper(), to_currency.upper()
        if f not in RATES_TO_INR or t not in RATES_TO_INR:
            return f"Unsupported currency. Supported: {', '.join(RATES_TO_INR)}"
        result = amount * RATES_TO_INR[f] / RATES_TO_INR[t]
        return f"{amount:g} {f} ~ {result:.2f} {t} (fixed approximate rates, not live)"

    return [
        add_transaction,
        list_transactions,
        spending_summary,
        set_budget,
        budget_status,
        delete_transaction,
        convert_currency,
    ]
