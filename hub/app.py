"""Hub: event bus for the UI, router that mirrors one PaymentRequest to both lanes, demo reset.

LEFT lane  = request goes straight to the rail (wallet L), no checks.
RIGHT lane = request goes to the Leash gateway, which alone can debit wallet R.
"""
import asyncio
from collections import deque

import httpx
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from shared.config import url
from shared.models import EVENT_TYPES, LANES
from shared.money import inr
from shared.timeutil import now_iso

app = FastAPI(title="Leash hub")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

LEFT_BLOCK = "blk_l_01"
EVENTS: deque = deque(maxlen=2000)
CLIENTS: set[WebSocket] = set()
_seq = 0
_mode = {"mode": "LIVE"}


async def publish(type_: str, lane: str, data: dict, ts: str | None = None) -> dict:
    global _seq
    _seq += 1
    ev = {"seq": _seq, "ts": ts or now_iso(), "lane": lane, "type": type_, "data": data}
    EVENTS.append(ev)
    dead = []
    for ws in list(CLIENTS):
        try:
            await ws.send_json(ev)
        except Exception:
            dead.append(ws)
    for ws in dead:
        CLIENTS.discard(ws)
    return ev


@app.get("/health")
async def health():
    return {"ok": True, "service": "hub", "seq": _seq, "clients": len(CLIENTS), **_mode}


# ------------------------------------------------------------------ events
@app.post("/events")
async def post_events(body: dict | list = Body(...)):
    items = body if isinstance(body, list) else [body]
    n = 0
    for e in items:
        if not isinstance(e, dict) or e.get("type") not in EVENT_TYPES or e.get("lane") not in LANES:
            continue
        await publish(e["type"], e["lane"], e.get("data") or {}, e.get("ts"))
        n += 1
    return {"accepted": n}


@app.get("/events")
async def get_events(since: int = 0):
    return {"events": [e for e in EVENTS if e["seq"] > since]}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    CLIENTS.add(websocket)
    try:
        for e in list(EVENTS)[-200:]:  # backfill so a refreshed screen catches up
            await websocket.send_json({**e, "backfill": True})
        while True:
            await websocket.receive_text()  # keepalive pings from the UI
    except WebSocketDisconnect:
        pass
    finally:
        CLIENTS.discard(websocket)


# ------------------------------------------------------------------ route (mirror)
async def _left(client: httpx.AsyncClient, req: dict) -> dict:
    try:
        r = await client.post(f"{url('rail')}/debit",
                              json={"block_id": LEFT_BLOCK, "authorizer": "agent", "request": req})
        body = r.json()
    except (httpx.HTTPError, ValueError) as e:
        return {"lane": "left", "paid": False, "amount_paise": 0, "error": str(e)}
    if r.status_code == 200:
        return {"lane": "left", "paid": True, "amount_paise": body["amount_paise"],
                "balance_paise": body["balance_paise"]}
    return {"lane": "left", "paid": False, "amount_paise": 0, "error": body.get("detail")}


async def _right(client: httpx.AsyncClient, req: dict) -> dict:
    try:
        r = await client.post(f"{url('gateway')}/pay", json=req)
        r.raise_for_status()
        d = r.json()
    except (httpx.HTTPError, ValueError) as e:
        return {"lane": "right", "paid": False, "amount_paise": 0, "error": str(e)}
    return {"lane": "right", "paid": d["outcome"] == "ALLOWED",
            "amount_paise": d["amount_debited_paise"], "decision": d}


@app.post("/route")
async def route(req: dict = Body(...)):
    """Mirror one signed PaymentRequest to both lanes and return both results."""
    cart = req.get("cart") if isinstance(req.get("cart"), list) else []
    await publish("request.created", "both", {
        "request_id": req.get("request_id"), "merchant": req.get("merchant"),
        "claimed_total_paise": req.get("claimed_total_paise"),
        "amount": inr(req["claimed_total_paise"]) if isinstance(req.get("claimed_total_paise"), int) else "?",
        "cart": [{"sku": i.get("sku"), "qty": i.get("qty"), "brand": i.get("brand"),
                  "family": i.get("family")} for i in cart if isinstance(i, dict)],
    })
    async with httpx.AsyncClient(timeout=5) as client:
        left, right = await asyncio.gather(_left(client, req), _right(client, req))
    return {"request_id": req.get("request_id"), "left": left, "right": right}


# ------------------------------------------------------------------ demo control
@app.post("/demo/reset")
async def demo_reset():
    """Reset every service to the seed state. Rail first: the gateway reads its block size."""
    global _seq
    out = {}
    async with httpx.AsyncClient(timeout=5) as client:
        for name, path in (("rail", "/demo/reset"), ("gateway", "/demo/reset"),
                           ("shops", "/admin/reset")):
            try:
                r = await client.post(f"{url(name)}{path}")
                out[name] = r.status_code == 200
            except httpx.HTTPError:
                out[name] = False
    EVENTS.clear()
    await publish("system.mode", "system", {"reset": True, **_mode, "services": out})
    return {"ok": all(out.values()), "services": out}


@app.post("/mode")
async def set_mode(body: dict = Body(...)):
    if body.get("mode") in ("LIVE", "REPLAY"):
        _mode["mode"] = body["mode"]
        await publish("system.mode", "system", dict(_mode))
    return _mode


# ------------------------------------------------------------------ preflight
@app.get("/preflight")
async def preflight():
    """Health of every dependency. `required` items gate `make demo-check`."""
    items = []

    def add(name, ok, detail="", required=True):
        items.append({"name": name, "ok": bool(ok), "detail": detail, "required": required})

    add("hub", True, f"{len(CLIENTS)} UI clients")
    async with httpx.AsyncClient(timeout=2) as client:
        health = {}
        for name in ("gateway", "rail", "shops"):
            try:
                r = await client.get(f"{url(name)}/health")
                health[name] = r.json()
                add(name, r.status_code == 200, url(name))
            except (httpx.HTTPError, ValueError) as e:
                add(name, False, f"{url(name)} unreachable ({e.__class__.__name__})")
        g = health.get("gateway", {})
        add("seed mandate", bool(g.get("mandate_id")), str(g.get("mandate_id")))
        chain = g.get("chain", {})
        add("log chain verifies", chain.get("ok"), f"{chain.get('length', 0)} entries")
        w = health.get("rail", {}).get("wallets", {})
        bal = {k: v.get("balance_paise") for k, v in w.items()}
        add("both wallets at ₹5,000", bal == {"L": 500000, "R": 500000},
            ", ".join(f"{k} {inr(v)}" for k, v in sorted(bal.items()) if isinstance(v, int)))
        try:
            r = await client.get("http://127.0.0.1:11434/api/tags")
            add("ollama", r.status_code == 200, "running", required=False)
        except httpx.HTTPError:
            add("ollama", False, "not running (needed from Phase 2)", required=False)
    ok = all(i["ok"] for i in items if i["required"])
    return {"ok": ok, "items": items}
