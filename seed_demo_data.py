"""Fill the database with ~3 months of realistic demo transactions and budgets.

    python seed_demo_data.py --user me

Run this once so you have data to ask questions about. Safe to re-run: it first removes
that user's existing rows.
"""

import argparse
import random
from datetime import date, timedelta

from finbuddy.db import connect

SPEND = {  # category -> (typical amount range, descriptions)
    "food": ((80, 450), ["lunch", "dinner", "swiggy order", "groceries", "coffee"]),
    "transport": ((30, 300), ["metro", "auto", "uber", "petrol"]),
    "entertainment": ((150, 900), ["movie", "netflix", "games", "concert"]),
    "shopping": ((300, 3000), ["clothes", "headphones", "books", "amazon order"]),
    "bills": ((200, 1500), ["electricity", "phone recharge", "wifi"]),
    "health": ((100, 1200), ["pharmacy", "gym", "doctor visit"]),
}


def seed(user: str, days: int = 90) -> int:
    random.seed(42)
    today = date.today()
    rows = []
    for offset in range(days):
        d = today - timedelta(days=offset)
        for _ in range(random.choice([0, 1, 1, 2, 3])):
            cat = random.choices(list(SPEND), weights=[6, 4, 2, 2, 1, 1])[0]
            (lo, hi), descs = SPEND[cat]
            rows.append((user, d.isoformat(), "expense", round(random.uniform(lo, hi), 2), cat, random.choice(descs)))
        if d.day == 1:
            rows.append((user, d.isoformat(), "income", 30000.0, "salary", "monthly pocket money / stipend"))
            rows.append((user, d.isoformat(), "expense", 8000.0, "rent", "room rent"))
    with connect() as c:
        c.execute("DELETE FROM transactions WHERE user_id = ?", (user,))
        c.execute("DELETE FROM budgets WHERE user_id = ?", (user,))
        c.executemany(
            "INSERT INTO transactions (user_id, date, kind, amount, category, description) VALUES (?,?,?,?,?,?)",
            rows,
        )
        c.executemany(
            "INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?,?,?)",
            [(user, "food", 6000), (user, "entertainment", 2000), (user, "shopping", 3000)],
        )
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="me")
    n = seed(ap.parse_args().user)
    print(f"Seeded {n} transactions and 3 budgets.")
