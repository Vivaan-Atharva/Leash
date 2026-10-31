"""Leash gateway: mandates, six checks, gateway-signed debits, hash-chained log.

No LLM anywhere in this service.
"""
import hashlib
import json
import threading
import time
from typing import Literal

import httpx
from fastapi import Body, FastAPI, HTTPException
from pydantic import ValidationError

from gateway import audit, catalog, checks, seed, store
from shared.canonical import canonical_json
from shared.config import url
from shared.crypto import sign_obj, verify_obj
from shared.events import emit
from shared.keys import public_key, signing_key
from shared.models import DECISION_UNSIGNED_FIELDS, Mandate, PaymentRequest
from shared.money import inr
from shared.timeutil import iso, now_iso, utcnow

app = FastAPI(title="Leash gateway")
LOCK = threading.Lock()  # decisions are serialised: one state, one order
_gw_key = None


def gw_key():
    global _gw_key
    if _gw_key is None:
        _gw_key = signing_key("gateway")
    return _gw_key


def _log(conn, type_: str, payload: dict) -> dict:
    e = audit.append(conn, type_, payload, now_iso())
    emit("log.appended", "right", {"index": e["index"], "type": type_, "hash": e["hash"]})
    return e


# ------------------------------------------------------------------ health & seed
@app.get("/health")
def health():
    with store.connect() as conn:
        mid = store.current_mandate_id(conn)
        return {"ok": True, "service": "gateway", "mandate_id": mid,
                "profile": store.kv_get(conn, "profile", "leash"),
                "chain": audit.verify(conn)}


def _store_mandate(conn, raw: dict) -> None:
    conn.execute("INSERT OR REPLACE INTO mandates VALUES (?,?,?,NULL)",
                 (raw["mandate_id"], json.dumps(raw), now_iso()))
    store.kv_set(conn, "current_mandate", raw["mandate_id"])
    _log(conn, "MANDATE_SIGNED", raw)


@app.post("/demo/reset")
def demo_reset():
    try:
        blk = httpx.get(f"{url('rail')}/blocks/{seed.RIGHT_BLOCK_ID}", timeout=2).json()
        block_amount = blk["amount_paise"]
    except (httpx.HTTPError, KeyError, ValueError):
        block_amount = 500000
    with LOCK, store.connect() as conn:
        store.wipe(conn)
        store.kv_set(conn, "profile", "leash")
        store.kv_set(conn, "block_amount", block_amount)
        conn.execute("INSERT INTO agents VALUES (?)", (public_key("agent"),))
        m = seed.seed_mandate()
        _store_mandate(conn, m)
    emit("mandate.signed", "right", {"mandate_id": m["mandate_id"], "seed": True})
    return {"ok": True, "mandate_id": m["mandate_id"]}


# ------------------------------------------------------------------ agents & mandates
@app.post("/agents/register")
def register_agent(body: dict = Body(...)):
    pk = body.get("pubkey")
    if not isinstance(pk, str) or not pk:
        raise HTTPException(400, "pubkey required")
    with store.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO agents VALUES (?)", (pk,))
    return {"ok": True}


@app.get("/agents/current")
def current_agent():
    """The agent key Asha's phone puts into the mandate it signs."""
    return {"agent_pubkey": public_key("agent")}


@app.get("/time")
def server_time():
    return {"now": now_iso()}


@app.post("/mandates")
def create_mandate(raw: dict = Body(...)):
    try:
        m = Mandate.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(422, f"malformed mandate: {e.errors()[:3]}")
    if not verify_obj(raw, m.user.phone_pubkey):
        raise HTTPException(401, "mandate signature does not verify with the phone key")
    with LOCK, store.connect() as conn:
        _store_mandate(conn, raw)
    emit("mandate.signed", "right", {"mandate_id": m.mandate_id, "user": m.user.name})
    return {"ok": True, "mandate_id": m.mandate_id}


@app.get("/mandates/current")
def current_mandate():
    with store.connect() as conn:
        mid = store.current_mandate_id(conn)
        if not mid:
            raise HTTPException(404, "no mandate")
        raw, revoked_at = store.get_mandate(conn, mid)
    return {"mandate": raw, "revoked_at": revoked_at,
            "status": "REVOKED" if revoked_at else "ACTIVE"}


@app.get("/mandates/{mandate_id}")
def get_mandate(mandate_id: str):
    with store.connect() as conn:
        raw, revoked_at = store.get_mandate(conn, mandate_id)
    if raw is None:
        raise HTTPException(404, "no such mandate")
    return {"mandate": raw, "revoked_at": revoked_at,
            "status": "REVOKED" if revoked_at else "ACTIVE"}


@app.post("/mandates/{mandate_id}/revoke")
def revoke_mandate(mandate_id: str, body: dict = Body(...)):
    """Body: {mandate_id, action: "revoke", ts, signature} signed by the phone key."""
    with LOCK, store.connect() as conn:
        raw, revoked_at = store.get_mandate(conn, mandate_id)
        if raw is None:
            raise HTTPException(404, "no such mandate")
        if body.get("mandate_id") != mandate_id or body.get("action") != "revoke":
            raise HTTPException(400, "revoke body must name this mandate and action=revoke")
        if not verify_obj(body, raw["user"]["phone_pubkey"]):
            raise HTTPException(401, "revoke must be signed by the mandate's phone key")
        if revoked_at:
            return {"ok": True, "revoked_at": revoked_at, "already": True}
        revoked_at = now_iso()
        conn.execute("UPDATE mandates SET revoked_at=? WHERE mandate_id=?", (revoked_at, mandate_id))
        _log(conn, "REVOKE", {"mandate_id": mandate_id, "revoked_at": revoked_at, "request": body})
    # Defence in depth: also close the reserve block on the rail (gateway-signed).
    rail_body = sign_obj({"block_id": raw["reserve_block_id"], "action": "revoke",
                          "ts": revoked_at}, gw_key())
    try:
        httpx.post(f"{url('rail')}/blocks/{raw['reserve_block_id']}/revoke", json=rail_body, timeout=2)
    except httpx.HTTPError:
        pass
    emit("mandate.revoked", "right", {"mandate_id": mandate_id, "revoked_at": revoked_at})
    return {"ok": True, "revoked_at": revoked_at}


# ------------------------------------------------------------------ profile
@app.get("/profile")
def get_profile():
    with store.connect() as conn:
        return {"profile": store.kv_get(conn, "profile", "leash")}


@app.post("/profile")
def set_profile(body: dict = Body(...)):
    p = body.get("profile")
    if p not in checks.PROFILES:
        raise HTTPException(400, f"profile must be one of {sorted(checks.PROFILES)}")
    with store.connect() as conn:
        store.kv_set(conn, "profile", p)
    return {"profile": p}


# ------------------------------------------------------------------ pay
def _decision_id(raw: dict, log_len: int) -> str:
    h = hashlib.sha256(canonical_json(raw) + str(log_len).encode()).hexdigest()
    return f"dec_{h[:8]}"


def _settle(decision_id: str, req: PaymentRequest, block_id: str) -> str | None:
    """Send a gateway-signed debit to the rail. Returns an error string or None."""
    debit = sign_obj({
        "debit_id": f"dbt_{decision_id}", "block_id": block_id,
        "amount_paise": req.claimed_total_paise, "merchant": req.merchant,
        "request_id": req.request_id, "decision_id": decision_id, "created_at": now_iso(),
    }, gw_key())
    try:
        r = httpx.post(f"{url('rail')}/debit", timeout=3,
                       json={"block_id": block_id, "authorizer": "gateway", "debit": debit})
    except httpx.HTTPError as e:
        return f"rail unreachable: {e.__class__.__name__}"
    if r.status_code != 200:
        return f"rail refused: {r.json().get('detail', r.text)}"
    return None


@app.post("/pay")
def pay(raw: dict = Body(...)):
    t0 = time.perf_counter_ns()
    with LOCK, store.connect() as conn:
        try:
            req = PaymentRequest.model_validate(raw)
        except ValidationError:
            req = None
        profile = store.kv_get(conn, "profile", "leash")
        mandate_raw, revoked_at = store.get_mandate(conn, raw.get("mandate_id", "")) \
            if isinstance(raw.get("mandate_id"), str) else (None, None)
        mandate = Mandate.model_validate(mandate_raw) if mandate_raw else None
        nonce = raw.get("nonce") if isinstance(raw.get("nonce"), str) else ""
        mid = mandate.mandate_id if mandate else ""
        state = checks.State(
            now=utcnow(),
            registered_agents=frozenset(r[0] for r in conn.execute("SELECT pubkey FROM agents")),
            revoked_at=revoked_at,
            nonce_seen=conn.execute("SELECT 1 FROM nonces WHERE nonce=?", (nonce,)).fetchone()
            is not None,
            week_spent_paise=store.week_spent(conn, mid),
            block_remaining_paise=store.kv_get(conn, "block_amount", 0) - _all_spent(conn),
            catalog=catalog.load(),
        )
        results = checks.run_checks(profile, req, mandate, state)
        outcome = checks.outcome(results)
        decided_in_us = (time.perf_counter_ns() - t0) // 1000

        # ---- record (outside the timed decision) ----
        log_len = conn.execute("SELECT COUNT(*) FROM log").fetchone()[0]
        decision_id = _decision_id(raw, log_len)
        if nonce:
            conn.execute("INSERT OR IGNORE INTO nonces VALUES (?,?,?)",
                         (nonce, raw.get("request_id"), now_iso()))
        _log(conn, "REQUEST", raw)

        settlement_error = None
        if outcome == "ALLOWED":
            block_id = mandate.reserve_block_id if mandate else seed.RIGHT_BLOCK_ID
            settlement_error = _settle(decision_id, req, block_id)
            if settlement_error:
                outcome = "BLOCKED"
        amount = req.claimed_total_paise if outcome == "ALLOWED" else 0

        decision = {
            "decision_id": decision_id,
            "request_id": raw.get("request_id"),
            "mandate_id": raw.get("mandate_id"),
            "merchant": raw.get("merchant"),
            "lane": "leash",
            "profile": profile,
            "outcome": outcome,
            "checks": [r.wire() for r in results],
            "amount_debited_paise": amount,
            "decided_in_us": decided_in_us,
            "decided_at": now_iso(),
            "settlement_error": settlement_error,
        }
        decision = sign_obj(decision, gw_key(), field="gateway_signature")
        entry = _log(conn, "DECISION", decision)
        if outcome == "ALLOWED":
            conn.execute("INSERT INTO spend VALUES (?,?,?,?)",
                         (decision_id, mid, amount, now_iso()))
            _log(conn, "DEBIT", {"decision_id": decision_id, "amount_paise": amount,
                                 "block_id": mandate.reserve_block_id, "merchant": req.merchant})
        decision["log_index"] = entry["index"]
        decision["log_hash"] = entry["hash"]
        conn.execute("INSERT OR REPLACE INTO decisions VALUES (?,?,?,?)",
                     (decision_id, raw.get("request_id"), json.dumps(decision), json.dumps(raw)))

    for r in results:
        emit("gateway.check", "right", {"decision_id": decision_id, **r.wire()})
    emit("gateway.decision", "right", {
        "decision_id": decision_id, "request_id": decision["request_id"], "outcome": outcome,
        "amount_paise": amount, "amount": inr(amount), "decided_in_us": decided_in_us,
        "failing": [r.n for r in results if not r.passed], "merchant": decision["merchant"],
        "reasons": [f"Check {r.n} · {r.name}: {r.detail}" for r in results if not r.passed],
        "checks": [r.wire() for r in results], "settlement_error": settlement_error,
        "log_index": decision["log_index"],
    })
    return decision


def _all_spent(conn) -> int:
    return conn.execute("SELECT COALESCE(SUM(amount_paise),0) FROM spend").fetchone()[0]


@app.get("/decisions/{decision_id}")
def get_decision(decision_id: str):
    with store.connect() as conn:
        row = conn.execute("SELECT decision, request FROM decisions WHERE decision_id=?",
                           (decision_id,)).fetchone()
    if not row:
        raise HTTPException(404, "no such decision")
    return {"decision": json.loads(row[0]), "request": json.loads(row[1])}


@app.get("/decisions/{decision_id}/verify")
def verify_decision(decision_id: str):
    d = get_decision(decision_id)["decision"]
    ok = verify_obj(d, public_key("gateway"), field="gateway_signature",
                    exclude=[f for f in DECISION_UNSIGNED_FIELDS if f != "gateway_signature"])
    return {"decision_id": decision_id, "signature_ok": ok}


# ------------------------------------------------------------------ log
@app.get("/log")
def get_log(from_: int = 1, limit: int = 500):
    with store.connect() as conn:
        return {"entries": audit.entries(conn, from_)[:limit]}


@app.get("/log/verify")
def log_verify():
    with store.connect() as conn:
        return audit.verify(conn)


@app.post("/demo/tamper")
def demo_tamper(body: dict = Body(default={})):
    """Demo only: flip one byte of an old log row directly in SQLite."""
    with LOCK, store.connect() as conn:
        if store.kv_get(conn, "tamper_backup"):
            raise HTTPException(409, "already tampered; restore first")
        n = conn.execute("SELECT COUNT(*) FROM log").fetchone()[0]
        if n == 0:
            raise HTTPException(409, "log is empty")
        idx = body.get("index") or max(1, n // 2)
        row = conn.execute("SELECT payload FROM log WHERE idx=?", (idx,)).fetchone()
        if not row:
            raise HTTPException(404, "no such index")
        store.kv_set(conn, "tamper_backup", {"index": idx, "payload": row[0]})
        conn.execute("UPDATE log SET payload=? WHERE idx=?", (audit.flip_one_byte(row[0]), idx))
        result = audit.verify(conn)
    emit("log.tampered", "system", {"index": idx, "tampered": True, **result})
    return {"tampered_index": idx, **result}


@app.post("/demo/restore")
def demo_restore():
    with LOCK, store.connect() as conn:
        b = store.kv_get(conn, "tamper_backup")
        if b:
            conn.execute("UPDATE log SET payload=? WHERE idx=?", (b["payload"], b["index"]))
            conn.execute("DELETE FROM kv WHERE key='tamper_backup'")
        result = audit.verify(conn)
    emit("log.tampered", "system", {"tampered": False, **result})
    return {"restored": bool(b), **result}
