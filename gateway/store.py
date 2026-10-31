"""Gateway SQLite storage. One file: data/gateway.db."""
import json
import sqlite3
from contextlib import contextmanager

from gateway import audit
from shared.config import data_dir

SCHEMA = [
    audit.SCHEMA,
    "CREATE TABLE IF NOT EXISTS mandates (mandate_id TEXT PRIMARY KEY, raw TEXT NOT NULL,"
    " created_at TEXT NOT NULL, revoked_at TEXT)",
    "CREATE TABLE IF NOT EXISTS agents (pubkey TEXT PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, request_id TEXT, seen_at TEXT)",
    "CREATE TABLE IF NOT EXISTS spend (decision_id TEXT PRIMARY KEY, mandate_id TEXT,"
    " amount_paise INTEGER, ts TEXT)",
    "CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY, request_id TEXT,"
    " decision TEXT NOT NULL, request TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)",
]
TABLES = ["log", "mandates", "agents", "nonces", "spend", "decisions", "kv"]


@contextmanager
def connect():
    conn = sqlite3.connect(data_dir() / "gateway.db", timeout=5)
    try:
        for stmt in SCHEMA:
            conn.execute(stmt)
        yield conn
        conn.commit()
    finally:
        conn.close()


def wipe(conn) -> None:
    for t in TABLES:
        conn.execute(f"DELETE FROM {t}")


def kv_get(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def kv_set(conn, key: str, value) -> None:
    conn.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (key, json.dumps(value)))


def get_mandate(conn, mandate_id: str):
    row = conn.execute("SELECT raw, revoked_at FROM mandates WHERE mandate_id=?",
                       (mandate_id,)).fetchone()
    return (json.loads(row[0]), row[1]) if row else (None, None)


def current_mandate_id(conn):
    return kv_get(conn, "current_mandate")


def week_spent(conn, mandate_id: str) -> int:
    return conn.execute("SELECT COALESCE(SUM(amount_paise),0) FROM spend WHERE mandate_id=?",
                        (mandate_id,)).fetchone()[0]
