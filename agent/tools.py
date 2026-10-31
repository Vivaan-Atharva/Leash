"""The agent's tools (spec §8). Shared by the scripted, LLM and replay agents.

Every mode goes through these, so every payment takes the same real path:
shop cart -> signed PaymentRequest -> hub /route -> both lanes.
"""
import secrets
import time

import httpx

from agent.provenance import Ledger, page_view, pick_culprit
from agent.scrape import scrape_segments
from shared.config import url


def shops_url() -> str:
    return url("shops")
from shared.crypto import pubkey_b64, random_nonce, sign_obj
from shared.keys import signing_key
from shared.timeutil import now_iso

SHOP_DOMAINS = {"freshcart": "freshcart.in", "dailybasket": "dailybasket.in", "freshkart": "fresh-kart.in"}
DOMAIN_TO_SHOP = {v: k for k, v in SHOP_DOMAINS.items()}


def shop_from_any(s: str) -> str:
    """Accept 'freshcart', 'freshcart.in', 'fresh-kart.in', 'FreshKart'."""
    s = (s or "").strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    if s in SHOP_DOMAINS:
        return s
    if s in DOMAIN_TO_SHOP:
        return DOMAIN_TO_SHOP[s]
    raise ValueError(f"unknown shop {s!r}; shops: {', '.join(SHOP_DOMAINS.values())}")


def parse_url(u: str) -> tuple[str, str]:
    """'https://fresh-kart.in/product/FK-MILK-AMUL-500' or '/freshcart/product/X' -> (shop, path)."""
    u = u.strip()
    for prefix in ("https://", "http://"):
        u = u.removeprefix(prefix)
    if u.startswith("/"):
        parts = u.lstrip("/").split("/", 1)
        return shop_from_any(parts[0]), "/" + (parts[1] if len(parts) > 1 else "")
    host, _, rest = u.partition("/")
    return shop_from_any(host), "/" + rest


class Tools:
    def __init__(self, http: httpx.Client | None = None, signer: str = "agent", on_event=None,
                 quiet: bool = False, dry_run: bool = False, scenario: str | None = None):
        self.http = http or httpx.Client(timeout=10)
        self.sk = signing_key(signer)
        self.last_request: dict | None = None
        self.routes: list[dict] = []
        self.on_event = on_event  # optional recorder hook: (type, data) -> None
        self.quiet = quiet        # counterfactual runs: record, don't broadcast
        self.dry_run = dry_run    # counterfactual runs: ask the gateway what it *would* decide; no money moves
        self.scenario = scenario
        self.ledger = Ledger()
        self.log: list[dict] = []  # everything this agent did, for counterfactual summaries
        self.traces: list[dict] = []

    def set_task(self, task: str) -> None:
        self.ledger.add_task(task)

    # ---- events -------------------------------------------------------
    def emit(self, type_: str, data: dict) -> None:
        if self.on_event:
            self.on_event(type_, data)
        if type_.startswith("agent."):
            self.log.append({"type": type_, **data})
        if self.quiet:
            return
        try:
            self.http.post(f"{url('hub')}/events", json={"type": type_, "lane": "both", "data": data})
        except httpx.HTTPError:
            pass

    def think(self, text: str) -> None:
        self.ledger.note_thought(text)
        self.emit("agent.thought", {"text": text})

    def call(self, name: str, args: dict) -> dict | str:
        """Run one tool by name, emitting tool_call and tool_result events."""
        fn = {"search_products": self.search_products, "get_page": self.get_page,
              "add_to_cart": self.add_to_cart, "view_cart": self.view_cart,
              "checkout": self.checkout}.get(name)
        self.emit("agent.tool_call", {"tool": name, "args": args})
        self.ledger.note_call(name, args)
        t0 = time.perf_counter()
        try:
            if fn is None:
                raise ValueError(f"no such tool {name}")
            result = fn(**args)
        except (ValueError, TypeError, KeyError, httpx.HTTPError) as e:
            result = {"error": f"{e.__class__.__name__}: {e}"}
        summary = result if isinstance(result, dict) else {"text": result[:400]}
        self.emit("agent.tool_result", {"tool": name, "ms": int((time.perf_counter() - t0) * 1000),
                                        "result": _short(summary)})
        return result

    # ---- tools --------------------------------------------------------
    def search_products(self, shop: str, query: str) -> dict:
        s = shop_from_any(shop)
        r = self.http.get(f"{url('shops')}/{s}/search", params={"q": query, "format": "json"})
        r.raise_for_status()
        return r.json()

    def get_page(self, url: str) -> str:
        shop, path = parse_url(url)
        r = self.http.get(f"{shops_url()}/{shop}{path}", params={"view": 1} if self.quiet else None)
        if r.status_code == 404:
            return f"404: page not found at {SHOP_DOMAINS[shop]}{path}"
        r.raise_for_status()
        segments = scrape_segments(r.text)
        self.ledger.add_page(f"{SHOP_DOMAINS[shop]}{path}", SHOP_DOMAINS[shop], segments)
        return f"[{SHOP_DOMAINS[shop]}{path}]\n" + "\n".join(s["text"] for s in segments)

    def add_to_cart(self, shop: str, sku: str, qty: int = 1) -> dict:
        s = shop_from_any(shop)
        r = self.http.post(f"{url('shops')}/{s}/cart", json={"sku": sku, "qty": int(qty)})
        if r.status_code != 200:
            return {"error": r.json().get("detail", r.text)}
        return r.json()

    def view_cart(self, shop: str) -> dict:
        s = shop_from_any(shop)
        return self.http.get(f"{url('shops')}/{s}/cart").json()

    def mandate_id(self) -> str:
        return self.http.get(f"{url('gateway')}/mandates/current").json()["mandate"]["mandate_id"]

    def checkout(self, shop: str) -> dict:
        """Build a PaymentRequest from the shop's cart, sign it, send it to hub /route."""
        s = shop_from_any(shop)
        cart = self.http.get(f"{url('shops')}/{s}/cart").json()
        if not cart["items"]:
            return {"error": "cart is empty"}
        req = {
            "request_id": f"req_{secrets.token_hex(3)}",
            "mandate_id": self.mandate_id(),
            "merchant": cart["merchant"],
            "cart": [{"sku": i["sku"], "family": i["family"], "brand": i["brand"],
                      "category": i["category"], "qty": i["qty"],
                      "claimed_unit_price_paise": i["unit_price_paise"]} for i in cart["items"]],
            "claimed_total_paise": cart["total_paise"],
            "nonce": random_nonce(),
            "created_at": now_iso(),
            "agent_pubkey": pubkey_b64(self.sk),
        }
        req = sign_obj(req, self.sk)
        self.http.post(f"{url('shops')}/{s}/cart/clear")
        fields = self.ledger.request_fields(req)
        routed = self.evaluate(req) if self.dry_run else self.send(req)
        self._trace(req, fields, routed)
        # What the agent learns back is only what a checkout page would tell it.
        return {"request_id": req["request_id"], "merchant": req["merchant"],
                "total": cart["total"], "status": "submitted"}

    def evaluate(self, req: dict) -> dict:
        """Dry run: what would each lane do? The gateway evaluates without logging or settling."""
        self.last_request = req
        d = self.http.post(f"{url('gateway')}/evaluate", json=req).json()
        routed = {"request_id": req["request_id"], "request": req, "dry_run": True,
                  "left": {"lane": "left", "paid": True, "amount_paise": req["claimed_total_paise"], "would": True},
                  "right": {"lane": "right", "paid": d["outcome"] == "ALLOWED",
                            "amount_paise": req["claimed_total_paise"] if d["outcome"] == "ALLOWED" else 0,
                            "decision": d}}
        self.routes.append(routed)
        return routed

    def _trace(self, req: dict, fields: list[dict], routed: dict) -> None:
        """The attack trace for one request: page → context → reasoning → tool call → request → lanes."""
        dec = routed["right"].get("decision", {})
        failing = [c["n"] for c in dec.get("checks", []) if not c["pass"]]
        ci = pick_culprit(fields, failing)
        culprit = fields[ci] if ci is not None else None
        call = (culprit or {}).get("call") or {}
        trace = {
            "request_id": req["request_id"], "scenario": self.scenario, "dry_run": self.dry_run,
            "page": page_view(self.ledger),
            "task": next((s["text"] for s in self.ledger.sources if s["trusted"]), None),
            "fields": [{k: f[k] for k in ("path", "field", "value", "display", "checks", "prov")} for f in fields],
            # The exact text the culprit value came from, wherever it was read (it may be an earlier page).
            "source": (lambda sid: None if sid is None else {
                k: self.ledger.sources[sid].get(k) for k in ("id", "text", "hidden", "url", "trusted")
            })((culprit or {}).get("prov", {}).get("source_id")),
            "culprit": ci,
            "thought": call.get("thought") or self.ledger.last_thought,
            "call": {"tool": call.get("tool"), "args": call.get("args")} if call else None,
            "total": req["claimed_total_paise"],
            "left": {"amount_paise": routed["left"]["amount_paise"], "paid": routed["left"].get("paid", False)},
            "right": {"outcome": dec.get("outcome"), "failing": failing, "decision_id": dec.get("decision_id"),
                      "checks": dec.get("checks", []), "amount_paise": routed["right"]["amount_paise"]},
        }
        self.traces.append(trace)
        if not self.quiet:
            try:
                self.http.post(f"{url('hub')}/events", json={"type": "attack.trace", "lane": "both", "data": trace})
            except httpx.HTTPError:
                pass

    def send(self, req: dict) -> dict:
        self.last_request = req
        r = self.http.post(f"{url('hub')}/route", json=req)
        r.raise_for_status()
        routed = r.json()
        routed["request"] = req  # keep what was asked for, so the eval can judge it
        self.routes.append(routed)
        return routed


def _short(obj, limit: int = 600):
    import json
    s = json.dumps(obj, ensure_ascii=False)
    return obj if len(s) <= limit else {"summary": s[:limit] + "…"}
