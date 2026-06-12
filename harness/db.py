import sqlite3
from pathlib import Path

HARNESS_HOME = Path.home() / ".harness-claude"
DB_PATH = HARNESS_HOME / "db.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS msg (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    from_role TEXT NOT NULL,
    to_role   TEXT NOT NULL,
    body      TEXT NOT NULL,
    created   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_unread ON msg(to_role) WHERE read_at IS NULL;
"""


def connect() -> sqlite3.Connection:
    HARNESS_HOME.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(str(DB_PATH), isolation_level=None, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
