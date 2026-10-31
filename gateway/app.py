"""Leash gateway: mandates, six checks, gateway-signed debits, hash-chained log.

No LLM anywhere in this service.
"""
import hashlib
import json
import threading
import time
from datetime import timedelta
from typing import Literal

import httpx
from fastapi import Body, FastAPI, HTTPException
from pydantic import ValidationError

from gateway import audit, catalog, checks, report, seed, store
from shared.canonical import canonical_json
from shared.config import url
from shared.crypto import fingerprint, sign_obj, verify_obj
from shared.events import emit
from shared.keys import public_key, signing_key
from shared.models import DECISION_UNSIGNED_FIELDS, Mandate, PaymentRequest
from shared.money import inr
from shared.timeutil import iso, now_iso, utcnow

app = FastAPI(title="Leash gateway")


@app.on_event("startup")
def _warm() -> None:
    """Load the catalogue and run one throwaway check pass so the first real decision is fast."""
    from shared.models import PaymentRequest as _PR  # noqa: F401
    catalog.load()
    try:
        m = Mandate.model_validate(seed.seed_mandate())
        st = checks.State(now=utcnow(), registered_agents=frozenset(), revoked_at=None, nonce_seen=False,
                          week_spent_paise=0, block_remaining_paise=0, catalog=catalog.load())
        checks.run_checks("leash", None, m, st)
        verify_obj(seed.seed_mandate(), m.user.phone_pubkey)
    except Exception:  # warm-up only; never block startup
        pass
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


STEP_UP_SECONDS = 60


def _record_brands(conn, mandate_id: str, req: PaymentRequest) -> None:
    ref = catalog.load()
    for it in req.cart:
        p = ref.get(catalog.product_key(it.sku))
        if p:
            conn.execute("INSERT OR IGNORE INTO brands VALUES (?,?,?)", (mandate_id, p["family"], p["brand"]))


def _decide(conn, raw: dict):
    """Everything up to the decision: parse, load state, run the checks, step-up. No side effects."""
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
        nonce_seen=conn.execute("SELECT 1 FROM nonces WHERE nonce=?", (nonce,)).fetchone() is not None,
        week_spent_paise=store.week_spent(conn, mid),
        block_remaining_paise=store.kv_get(conn, "block_amount", 0) - store.all_committed(conn),
        catalog=catalog.load(),
    )
    results = checks.run_checks(profile, req, mandate, state)
    outcome = checks.outcome(results)
    step_up = None
    if outcome == "ALLOWED" and profile == "leash" and store.kv_get(conn, "stepup", True):
        known = frozenset(checks.usual_brands(mandate) | store.known_brands(conn, mid))
        reason = checks.step_up_reason(req, mandate, state, known)
        if reason:
            outcome = "HELD"
            step_up = {"reason": reason, "expires_at": iso(state.now + timedelta(seconds=STEP_UP_SECONDS))}
    return req, mandate, mid, nonce, profile, results, outcome, step_up


@app.post("/evaluate")
def evaluate(raw: dict = Body(...)):
    """What *would* Leash decide? Same checks as /pay, but nothing is logged, recorded or settled.
    Used by counterfactual replays ("the same agent on the same page without the hidden text")."""
    t0 = time.perf_counter_ns()
    with LOCK, store.connect() as conn:
        _, _, _, _, profile, results, outcome, step_up = _decide(conn, raw)
    return {"dry_run": True, "request_id": raw.get("request_id"), "profile": profile, "outcome": outcome,
            "checks": [r.wire() for r in results], "step_up": step_up,
            "decided_in_us": (time.perf_counter_ns() - t0) // 1000}


@app.post("/pay")
def pay(raw: dict = Body(...)):
    t0 = time.perf_counter_ns()
    with LOCK, store.connect() as conn:
        req, mandate, mid, nonce, profile, results, outcome, step_up = _decide(conn, raw)
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
            "step_up": step_up,
        }
        decision = sign_obj(decision, gw_key(), field="gateway_signature")
        entry = _log(conn, "DECISION", decision)
        if outcome == "ALLOWED":
            conn.execute("INSERT INTO spend VALUES (?,?,?,?)",
                         (decision_id, mid, amount, now_iso()))
            _record_brands(conn, mid, req)
            _log(conn, "DEBIT", {"decision_id": decision_id, "amount_paise": amount,
                                 "block_id": mandate.reserve_block_id, "merchant": req.merchant})
        if outcome == "HELD":
            conn.execute("INSERT INTO stepups VALUES (?,?,?,?,?,NULL)",
                         (decision_id, mid, req.claimed_total_paise, "PENDING", step_up["expires_at"]))
            _log(conn, "STEP_UP_REQUESTED", {"decision_id": decision_id, **step_up,
                                             "amount_paise": req.claimed_total_paise})
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
        "log_index": decision["log_index"], "step_up": step_up,
    })
    if outcome == "HELD":
        emit("stepup.requested", "right", {
            "decision_id": decision_id, "mandate_id": mid, "merchant": req.merchant,
            "amount_paise": req.claimed_total_paise, "amount": inr(req.claimed_total_paise),
            "reason": step_up["reason"], "expires_at": step_up["expires_at"],
            "items": [{"brand": i.brand, "family": i.family, "qty": i.qty,
                       "unit": inr(i.claimed_unit_price_paise)} for i in req.cart]})
        t = threading.Timer(STEP_UP_SECONDS, _timeout_stepup, args=(decision_id,))
        t.daemon = True
        t.start()
    return decision


# ------------------------------------------------------------------ step-up
def _resolve(decision_id: str, approve: bool, by: str) -> dict:
    with LOCK, store.connect() as conn:
        row = conn.execute("SELECT status, mandate_id, amount_paise FROM stepups WHERE decision_id=?",
                           (decision_id,)).fetchone()
        if not row:
            raise HTTPException(404, "no step-up for this decision")
        status, mid, amount = row
        if status != "PENDING":
            raise HTTPException(409, f"already resolved: {status}")
        drow = conn.execute("SELECT request FROM decisions WHERE decision_id=?", (decision_id,)).fetchone()
        req = PaymentRequest.model_validate(json.loads(drow[0]))
        mandate_raw, revoked_at = store.get_mandate(conn, mid)
        error = None
        if approve and revoked_at:
            error = "mandate revoked while waiting for approval"
        elif approve:
            error = _settle(decision_id, req, mandate_raw["reserve_block_id"])
        outcome = "ALLOWED" if approve and not error else "BLOCKED"
        paid = amount if outcome == "ALLOWED" else 0
        resolution = sign_obj({
            "decision_id": decision_id, "outcome": outcome, "resolved_by": by,
            "resolved_at": now_iso(), "amount_debited_paise": paid, "error": error,
        }, gw_key(), field="gateway_signature")
        conn.execute("UPDATE stepups SET status=?, resolution=? WHERE decision_id=?",
                     (outcome, json.dumps(resolution), decision_id))
        _log(conn, "STEP_UP_RESOLVED", resolution)
        if outcome == "ALLOWED":
            conn.execute("INSERT INTO spend VALUES (?,?,?,?)", (decision_id, mid, paid, now_iso()))
            _record_brands(conn, mid, req)
            _log(conn, "DEBIT", {"decision_id": decision_id, "amount_paise": paid,
                                 "block_id": mandate_raw["reserve_block_id"], "merchant": req.merchant})
    emit("stepup.resolved", "right", {"decision_id": decision_id, "outcome": outcome, "by": by,
                                      "amount_paise": paid, "amount": inr(paid), "error": error})
    return resolution


def _timeout_stepup(decision_id: str) -> None:
    try:
        _resolve(decision_id, False, "timeout")
    except HTTPException:
        pass  # already resolved on the phone


# Declared before /stepup/{decision_id} so "config" isn't read as a decision id.
@app.post("/stepup/config")
def stepup_config(body: dict = Body(...)):
    with store.connect() as conn:
        store.kv_set(conn, "stepup", bool(body.get("enabled", True)))
        return {"enabled": store.kv_get(conn, "stepup", True)}


@app.post("/stepup/{decision_id}")
def stepup(decision_id: str, body: dict = Body(...)):
    """Body: {decision_id, approve: bool, ts, signature} signed by the mandate's phone key."""
    with store.connect() as conn:
        row = conn.execute("SELECT mandate_id FROM stepups WHERE decision_id=?", (decision_id,)).fetchone()
        if not row:
            raise HTTPException(404, "no step-up for this decision")
        mandate_raw, _ = store.get_mandate(conn, row[0])
    if body.get("decision_id") != decision_id or not isinstance(body.get("approve"), bool):
        raise HTTPException(400, "body must name this decision and approve=true/false")
    if not verify_obj(body, mandate_raw["user"]["phone_pubkey"]):
        raise HTTPException(401, "approval must be signed by the mandate's phone key")
    return _resolve(decision_id, body["approve"], "phone")


@app.get("/stepup/pending")
def stepup_pending():
    with store.connect() as conn:
        rows = conn.execute("SELECT decision_id, amount_paise, expires_at FROM stepups WHERE status='PENDING'")
        return {"pending": [{"decision_id": d, "amount_paise": a, "expires_at": e} for d, a, e in rows]}


@app.get("/decisions/{decision_id}")
def get_decision(decision_id: str):
    with store.connect() as conn:
        row = conn.execute("SELECT decision, request FROM decisions WHERE decision_id=?",
                           (decision_id,)).fetchone()
    if not row:
        raise HTTPException(404, "no such decision")
    return {"decision": json.loads(row[0]), "request": json.loads(row[1])}


@app.get("/report/{decision_id}")
def get_report(decision_id: str):
    """Everything a dispute needs: signed mandate, signed request, the checks, the chain, a verdict."""
    with store.connect() as conn:
        row = conn.execute("SELECT decision, request FROM decisions WHERE decision_id=?",
                           (decision_id,)).fetchone()
        if not row:
            raise HTTPException(404, "no such decision")
        decision, request = json.loads(row[0]), json.loads(row[1])
        mandate, revoked_at = store.get_mandate(conn, decision.get("mandate_id") or "")
        srow = conn.execute("SELECT resolution FROM stepups WHERE decision_id=?", (decision_id,)).fetchone()
        resolution = json.loads(srow[0]) if srow and srow[0] else None
        chain = audit.verify(conn)
        entries = audit.entries(conn)
    gw_pub = public_key("gateway")
    signed_decision = {k: v for k, v in decision.items() if k not in ("log_index", "log_hash")}
    log_entry = next((e for e in entries if e["index"] == decision.get("log_index")), None)
    related = {decision_id, request.get("request_id")}
    timeline = [
        {"index": e["index"], "timestamp": e["timestamp"], "type": e["type"], "hash": e["hash"]}
        for e in entries
        if (e["type"] == "MANDATE_SIGNED" and e["payload"].get("mandate_id") == decision.get("mandate_id"))
        or (e["type"] == "REVOKE" and e["payload"].get("mandate_id") == decision.get("mandate_id"))
        or e["payload"].get("request_id") in related or e["payload"].get("decision_id") in related
    ]
    return {
        "decision": decision,
        "request": request,
        "mandate": mandate,
        "mandate_status": "REVOKED" if revoked_at else "ACTIVE",
        "revoked_at": revoked_at,
        "resolution": resolution,
        "signatures": {
            "mandate": bool(mandate) and verify_obj(mandate, mandate["user"]["phone_pubkey"]),
            "request": isinstance(request.get("agent_pubkey"), str) and verify_obj(request, request["agent_pubkey"]),
            "request_key_in_mandate": bool(mandate) and request.get("agent_pubkey") == mandate["agent_pubkey"],
            "decision": verify_obj(signed_decision, gw_pub, field="gateway_signature"),
            "resolution": verify_obj(resolution, gw_pub, field="gateway_signature") if resolution else None,
        },
        "fingerprints": {
            "phone_key": fingerprint(mandate["user"]["phone_pubkey"]) if mandate else None,
            "agent_key": fingerprint(request.get("agent_pubkey", "")),
            "gateway_key": fingerprint(gw_pub),
            "mandate_signature": fingerprint(mandate["signature"]) if mandate else None,
            "request_signature": fingerprint(request.get("signature", "")),
            "decision_signature": fingerprint(decision.get("gateway_signature", "")),
        },
        "chain": {**chain, "decision_entry_matches": bool(log_entry) and log_entry["payload"] == signed_decision
                  and log_entry["hash"] == decision.get("log_hash")},
        "timeline": timeline,
        "verdict": report.verdict(decision, resolution, revoked_at),
    }


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
