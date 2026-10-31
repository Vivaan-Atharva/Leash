"""The agent's tools (spec §8). Shared by the scripted, LLM and replay agents.

Every mode goes through these, so every payment takes the same real path:
shop cart -> signed PaymentRequest -> hub /route -> both lanes.
"""
import secrets
import time

import httpx

from agent.scrape import scrape_text
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
    def __init__(self, http: httpx.Client | None = None, signer: str = "agent", on_event=None):
        self.http = http or httpx.Client(timeout=10)
        self.sk = signing_key(signer)
        self.last_request: dict | None = None
        self.routes: list[dict] = []
        self.on_event = on_event  # optional recorder hook: (type, data) -> None

    # ---- events -------------------------------------------------------
    def emit(self, type_: str, data: dict) -> None:
        if self.on_event:
            self.on_event(type_, data)
        try:
            self.http.post(f"{url('hub')}/events", json={"type": type_, "lane": "both", "data": data})
        except httpx.HTTPError:
            pass

    def think(self, text: str) -> None:
        self.emit("agent.thought", {"text": text})

    def call(self, name: str, args: dict) -> dict | str:
        """Run one tool by name, emitting tool_call and tool_result events."""
        fn = {"search_products": self.search_products, "get_page": self.get_page,
              "add_to_cart": self.add_to_cart, "view_cart": self.view_cart,
              "checkout": self.checkout}.get(name)
        self.emit("agent.tool_call", {"tool": name, "args": args})
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
        r = self.http.get(f"{shops_url()}/{shop}{path}")
        if r.status_code == 404:
            return f"404: page not found at {SHOP_DOMAINS[shop]}{path}"
        r.raise_for_status()
        return f"[{SHOP_DOMAINS[shop]}{path}]\n" + scrape_text(r.text)

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
        self.send(req)
        # What the agent learns back is only what a checkout page would tell it.
        return {"request_id": req["request_id"], "merchant": req["merchant"],
                "total": cart["total"], "status": "submitted"}

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
