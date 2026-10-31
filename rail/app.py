"""Mock UPI Reserve Pay rail.

Wallet L (blk_l_01): accepts debits authorised by any agent-signed payment request.
Wallet R (blk_r_01): requires_gateway_sig, so only debits co-signed by the gateway key move money.
"""
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import timedelta

from fastapi import Body, FastAPI, HTTPException

from shared.config import data_dir
from shared.crypto import verify_obj
from shared.events import emit
from shared.keys import public_key
from shared.money import inr
from shared.timeutil import iso, now_iso, utcnow

app = FastAPI(title="Leash mock rail (UPI Reserve Pay)")
LOCK = threading.Lock()
SEED_BALANCE = 500000  # ₹5,000 per wallet
SEED_BLOCKS = [("blk_l_01", "L", False), ("blk_r_01", "R", True)]
LANE = {"L": "left", "R": "right"}

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS blocks (block_id TEXT PRIMARY KEY, wallet TEXT, amount_paise INTEGER,"
    " remaining_paise INTEGER, expires_at TEXT, requires_gateway_sig INTEGER, status TEXT,"
    " revoked_at TEXT)",
    "CREATE TABLE IF NOT EXISTS debits (debit_id TEXT PRIMARY KEY, block_id TEXT, amount_paise INTEGER,"
    " merchant TEXT, request_id TEXT, authorizer TEXT, ts TEXT, proof TEXT)",
]


@contextmanager
def connect():
    conn = sqlite3.connect(data_dir() / "rail.db", timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        for s in SCHEMA:
            conn.execute(s)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _block(conn, block_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM blocks WHERE block_id=?", (block_id,)).fetchone()
    return dict(row) if row else None


def _seed(conn) -> None:
    conn.execute("DELETE FROM blocks")
    conn.execute("DELETE FROM debits")
    exp = iso(utcnow() + timedelta(days=7))
    for bid, wallet, gw in SEED_BLOCKS:
        conn.execute("INSERT INTO blocks VALUES (?,?,?,?,?,?,?,NULL)",
                     (bid, wallet, SEED_BALANCE, SEED_BALANCE, exp, int(gw), "ACTIVE"))


@app.get("/health")
def health():
    with connect() as conn:
        return {"ok": True, "service": "rail", "wallets": _wallets(conn)}


def _wallets(conn) -> dict:
    return {r["wallet"]: {"block_id": r["block_id"], "balance_paise": r["remaining_paise"],
                          "status": r["status"]}
            for r in conn.execute("SELECT * FROM blocks WHERE block_id IN ('blk_l_01','blk_r_01')")}


@app.get("/wallets")
def wallets():
    with connect() as conn:
        return _wallets(conn)


@app.post("/demo/reset")
def reset():
    with LOCK, connect() as conn:
        _seed(conn)
        w = _wallets(conn)
    for wallet, v in w.items():
        emit("rail.balance", LANE[wallet], {"block_id": v["block_id"], "balance_paise": v["balance_paise"]})
    return {"ok": True, "wallets": w}


@app.post("/blocks")
def create_block(body: dict = Body(...)):
    amount = body.get("amount_paise")
    if not isinstance(amount, int) or amount <= 0:
        raise HTTPException(400, "amount_paise must be a positive integer")
    bid = body.get("block_id") or f"blk_{secrets.token_hex(3)}"
    exp = body.get("expires_at") or iso(utcnow() + timedelta(days=7))
    with LOCK, connect() as conn:
        conn.execute("INSERT INTO blocks VALUES (?,?,?,?,?,?,?,NULL)",
                     (bid, body.get("wallet", "X"), amount, amount, exp,
                      int(bool(body.get("requires_gateway_sig", True))), "ACTIVE"))
        return _block(conn, bid)


@app.get("/blocks/{block_id}")
def get_block(block_id: str):
    with connect() as conn:
        b = _block(conn, block_id)
        if not b:
            raise HTTPException(404, "no such block")
        b["debits"] = [dict(r) for r in conn.execute(
            "SELECT debit_id, amount_paise, merchant, request_id, authorizer, ts FROM debits"
            " WHERE block_id=? ORDER BY ts", (block_id,))]
        b["requires_gateway_sig"] = bool(b["requires_gateway_sig"])
        return b


@app.post("/blocks/{block_id}/revoke")
def revoke_block(block_id: str, body: dict = Body(default={})):
    with LOCK, connect() as conn:
        b = _block(conn, block_id)
        if not b:
            raise HTTPException(404, "no such block")
        if not b["requires_gateway_sig"]:
            # Mirrors Reserve Pay today: the user can't cancel a block directly.
            raise HTTPException(409, "revoke must go through merchant")
        if not (body.get("block_id") == block_id and body.get("action") == "revoke"
                and verify_obj(body, public_key("gateway"))):
            raise HTTPException(401, "revoke must be signed by the gateway")
        ts = now_iso()
        conn.execute("UPDATE blocks SET status='REVOKED', revoked_at=? WHERE block_id=?", (ts, block_id))
    return {"ok": True, "block_id": block_id, "revoked_at": ts}


@app.post("/debit")
def debit(body: dict = Body(...)):
    """Two shapes:
    left:  {block_id, authorizer: "agent",   request: <agent-signed PaymentRequest>}
    right: {block_id, authorizer: "gateway", debit: <gateway-signed debit>}
    """
    block_id = body.get("block_id")
    authorizer = body.get("authorizer")
    with LOCK, connect() as conn:
        b = _block(conn, block_id) if isinstance(block_id, str) else None
        if not b:
            raise HTTPException(404, "no such block")

        if b["requires_gateway_sig"]:
            d = body.get("debit")
            if authorizer != "gateway" or not isinstance(d, dict):
                raise HTTPException(403, "this block only accepts gateway-signed debits")
            if not verify_obj(d, public_key("gateway")):
                raise HTTPException(403, "bad gateway signature")
            if d.get("block_id") != block_id:
                raise HTTPException(403, "debit was signed for a different block")
            debit_id, amount = d.get("debit_id"), d.get("amount_paise")
            merchant, request_id, proof = d.get("merchant"), d.get("request_id"), d
        else:
            r = body.get("request")
            if not isinstance(r, dict) or not isinstance(r.get("agent_pubkey"), str):
                raise HTTPException(400, "agent-signed request required")
            # The unprotected wallet trusts whatever key signed the request.
            if not verify_obj(r, r["agent_pubkey"]):
                raise HTTPException(403, "bad agent signature")
            debit_id = f"dbt_l_{secrets.token_hex(4)}"
            amount, merchant, request_id, proof = (r.get("claimed_total_paise"), r.get("merchant"),
                                                   r.get("request_id"), r)

        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise HTTPException(400, "amount must be a positive integer (paise)")
        if b["status"] != "ACTIVE":
            raise HTTPException(409, f"block {b['status'].lower()}")
        if amount > b["remaining_paise"]:
            raise HTTPException(409, "insufficient funds in block")
        if conn.execute("SELECT 1 FROM debits WHERE debit_id=?", (debit_id,)).fetchone():
            raise HTTPException(409, "duplicate debit")
        ts = now_iso()
        conn.execute("INSERT INTO debits VALUES (?,?,?,?,?,?,?,?)",
                     (debit_id, block_id, amount, merchant, request_id, authorizer, ts, json.dumps(proof)))
        conn.execute("UPDATE blocks SET remaining_paise = remaining_paise - ? WHERE block_id=?",
                     (amount, block_id))
        balance = _block(conn, block_id)["remaining_paise"]

    lane = LANE.get(b["wallet"], "system")
    emit("rail.debit", lane, {"debit_id": debit_id, "block_id": block_id, "amount_paise": amount,
                              "amount": inr(amount), "merchant": merchant, "request_id": request_id})
    emit("rail.balance", lane, {"block_id": block_id, "balance_paise": balance})
    return {"ok": True, "debit_id": debit_id, "amount_paise": amount, "balance_paise": balance}
