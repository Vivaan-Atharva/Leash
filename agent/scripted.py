"""Scripted, deterministic agent (Phase 1). No LLM: it performs each scenario's steps exactly.

It uses the same shop endpoints and the same checkout path the LLM agent will use.
"""
import secrets

import httpx

from agent.scrape import scrape_text
from shared.config import url
from shared.crypto import pubkey_b64, random_nonce, sign_obj
from shared.keys import signing_key
from shared.timeutil import now_iso


class ScriptedAgent:
    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=10)
        self.keys = {"agent": signing_key("agent"), "rogue": signing_key("rogue")}
        self.last_request: dict | None = None

    # ---- events -------------------------------------------------------
    def think(self, text: str) -> None:
        self.emit("agent.thought", {"text": text})

    def emit(self, type_: str, data: dict) -> None:
        try:
            self.http.post(f"{url('hub')}/events", json={"type": type_, "lane": "both", "data": data})
        except httpx.HTTPError:
            pass

    # ---- tools (same names as the LLM tools in spec §8) ---------------
    def get_page(self, shop: str, sku: str) -> str:
        self.emit("agent.tool_call", {"tool": "get_page", "args": {"url": f"/{shop}/product/{sku}"}})
        r = self.http.get(f"{url('shops')}/{shop}/product/{sku}")
        r.raise_for_status()
        return scrape_text(r.text)

    def add_to_cart(self, shop: str, sku: str, qty: int) -> dict:
        self.emit("agent.tool_call", {"tool": "add_to_cart", "args": {"shop": shop, "sku": sku, "qty": qty}})
        r = self.http.post(f"{url('shops')}/{shop}/cart", json={"sku": sku, "qty": qty})
        r.raise_for_status()
        return r.json()

    def mandate_id(self) -> str:
        return self.http.get(f"{url('gateway')}/mandates/current").json()["mandate"]["mandate_id"]

    def checkout(self, shop: str, signer: str = "agent") -> dict:
        """Build a PaymentRequest from the shop's cart, sign it, send it to hub /route."""
        self.emit("agent.tool_call", {"tool": "checkout", "args": {"shop": shop}})
        cart = self.http.get(f"{url('shops')}/{shop}/cart").json()
        sk = self.keys[signer]
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
            "agent_pubkey": pubkey_b64(sk),
        }
        req = sign_obj(req, sk)
        self.http.post(f"{url('shops')}/{shop}/cart/clear")
        return self.send(req)

    def send(self, req: dict) -> dict:
        self.last_request = req
        r = self.http.post(f"{url('hub')}/route", json=req)
        r.raise_for_status()
        return r.json()
