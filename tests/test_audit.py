import sqlite3

from gateway import audit


def make_log(n=5):
    conn = sqlite3.connect(":memory:")
    conn.execute(audit.SCHEMA)
    for i in range(n):
        audit.append(conn, "REQUEST", {"i": i, "amount_paise": 9600}, f"2026-10-31T11:0{i}:00Z")
    return conn


def test_append_and_verify():
    conn = make_log()
    rows = audit.entries(conn)
    assert rows[0]["prev_hash"] == audit.GENESIS
    assert all(rows[i]["prev_hash"] == rows[i - 1]["hash"] for i in range(1, len(rows)))
    assert audit.verify(conn) == {"ok": True, "broken_at": None, "length": 5}


def test_single_changed_byte_is_detected():
    conn = make_log()
    payload = conn.execute("SELECT payload FROM log WHERE idx=3").fetchone()[0]
    flipped = audit.flip_one_byte(payload)
    assert sum(a != b for a, b in zip(payload, flipped)) == 1 and len(payload) == len(flipped)
    conn.execute("UPDATE log SET payload=? WHERE idx=3", (flipped,))
    assert audit.verify(conn) == {"ok": False, "broken_at": 3, "length": 5}


def test_changed_hash_or_deleted_row_detected():
    conn = make_log()
    conn.execute("UPDATE log SET hash=? WHERE idx=2", ("f" * 64,))
    assert audit.verify(conn)["broken_at"] == 2
    conn = make_log()
    conn.execute("DELETE FROM log WHERE idx=2")
    assert audit.verify(conn)["broken_at"] == 3


def test_unknown_type_refused():
    import pytest
    with pytest.raises(ValueError):
        audit.append(make_log(0), "NOPE", {}, "t")
