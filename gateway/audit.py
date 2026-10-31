"""Hash-chained audit log (spec §3.4).

hash = sha256(prev_hash || canonical_json({index, timestamp, type, payload, prev_hash}))
The payload is stored as canonical JSON text so a single changed byte is detectable.
"""
import hashlib
import json
import sqlite3

from shared.canonical import canonical_json

GENESIS = "0" * 64
TYPES = {"MANDATE_SIGNED", "REQUEST", "DECISION", "DEBIT", "REVOKE",
         "STEP_UP_REQUESTED", "STEP_UP_RESOLVED"}

SCHEMA = """CREATE TABLE IF NOT EXISTS log (
  idx INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, type TEXT NOT NULL,
  payload TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL)"""
# Merkle leaf hashes, written at append time (see gateway/merkle.py). Never recomputed from the log,
# so editing a log row later can't silently update its leaf.
MERKLE_SCHEMA = "CREATE TABLE IF NOT EXISTS merkle_leaves (idx INTEGER PRIMARY KEY, leaf TEXT NOT NULL)"
SCHEMAS = [SCHEMA, MERKLE_SCHEMA]


def entry_hash(index: int, timestamp: str, type_: str, payload: dict, prev_hash: str) -> str:
    body = {"index": index, "timestamp": timestamp, "type": type_,
            "payload": payload, "prev_hash": prev_hash}
    return hashlib.sha256(prev_hash.encode() + canonical_json(body)).hexdigest()


def append(conn: sqlite3.Connection, type_: str, payload: dict, timestamp: str) -> dict:
    if type_ not in TYPES:
        raise ValueError(f"unknown log type {type_}")
    row = conn.execute("SELECT idx, hash FROM log ORDER BY idx DESC LIMIT 1").fetchone()
    index, prev = (row[0] + 1, row[1]) if row else (1, GENESIS)
    h = entry_hash(index, timestamp, type_, payload, prev)
    conn.execute("INSERT INTO log VALUES (?,?,?,?,?,?)",
                 (index, timestamp, type_, canonical_json(payload).decode(), prev, h))
    from gateway import merkle
    leaf = merkle.leaf_hash(merkle.leaf_bytes(index, timestamp, type_, payload, prev)).hex()
    conn.execute("INSERT INTO merkle_leaves VALUES (?,?)", (index, leaf))
    return {"index": index, "timestamp": timestamp, "type": type_,
            "payload": payload, "prev_hash": prev, "hash": h}


def verify(conn: sqlite3.Connection) -> dict:
    """Walk the chain. Returns {ok, broken_at, length}."""
    expected_prev, expected_idx, n = GENESIS, 1, 0
    for idx, ts, type_, payload_text, prev, h in conn.execute(
            "SELECT idx, timestamp, type, payload, prev_hash, hash FROM log ORDER BY idx"):
        n += 1
        try:
            payload = json.loads(payload_text)
            good = (idx == expected_idx and prev == expected_prev
                    and canonical_json(payload).decode() == payload_text
                    and entry_hash(idx, ts, type_, payload, prev) == h)
        except (ValueError, TypeError):
            good = False
        if not good:
            return {"ok": False, "broken_at": idx, "length": _count(conn)}
        expected_prev, expected_idx = h, idx + 1
    return {"ok": True, "broken_at": None, "length": n}


def _count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM log").fetchone()[0]


def entries(conn: sqlite3.Connection, from_idx: int = 1) -> list[dict]:
    out = []
    for idx, ts, type_, payload, prev, h in conn.execute(
            "SELECT idx, timestamp, type, payload, prev_hash, hash FROM log WHERE idx >= ? ORDER BY idx",
            (from_idx,)):
        try:
            p = json.loads(payload)
        except ValueError:
            p = {"_raw": payload}
        out.append({"index": idx, "timestamp": ts, "type": type_, "payload": p,
                    "prev_hash": prev, "hash": h})
    return out


def flip_one_byte(text: str) -> str:
    """Change exactly one character, keeping the JSON parseable: bump the first digit."""
    for i, ch in enumerate(text):
        if ch.isdigit():
            return text[:i] + str((int(ch) + 1) % 10) + text[i + 1:]
    i = text.index('"') + 1
    return text[:i] + ("x" if text[i] != "x" else "y") + text[i + 1:]
