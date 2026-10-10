"""SQLite storage for FinBuddy (transactions + budgets).

The agent's long-term data lives here. Conversation memory lives separately in the
LangGraph checkpointer (see main.py), so the agent remembers both the chat and the data.
"""

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("FINBUDDY_DB", "finbuddy.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT    NOT NULL,
    date        TEXT    NOT NULL,                       -- YYYY-MM-DD
    kind        TEXT    NOT NULL CHECK (kind IN ('expense', 'income')),
    amount      REAL    NOT NULL CHECK (amount > 0),
    category    TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_txn_user_date ON transactions (user_id, date);

CREATE TABLE IF NOT EXISTS budgets (
    user_id       TEXT NOT NULL,
    category      TEXT NOT NULL,
    monthly_limit REAL NOT NULL CHECK (monthly_limit > 0),
    PRIMARY KEY (user_id, category)
);
"""


@contextmanager
def connect(path: str | None = None):
    """Open a connection, commit on success, always close."""
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()
