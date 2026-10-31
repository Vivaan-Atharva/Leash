"""Scripted, deterministic agent: performs a scenario's steps exactly. No LLM.

Used by tests, `make scenario`, and as the last-resort fallback (badge: SCRIPTED).
"""
import httpx

from agent.tools import Tools


class ScriptedAgent:
    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=10)
        self.tools = {"agent": Tools(self.http, "agent"), "rogue": Tools(self.http, "rogue")}
        self.last_request: dict | None = None

    def set_task(self, task: str, scenario: str | None = None) -> None:
        for t in self.tools.values():
            t.set_task(task)
            t.scenario = scenario

    def emit(self, type_: str, data: dict) -> None:
        self.tools["agent"].emit(type_, data)

    def think(self, text: str) -> None:
        self.tools["agent"].think(text)

    def get_page(self, shop: str, sku: str) -> str:
        # Both signers share what the model has read (the rogue key signs the same agent's requests).
        out = self.tools["agent"].call("get_page", {"url": f"/{shop}/product/{sku}"})
        self.tools["rogue"].ledger = self.tools["agent"].ledger
        return out

    def add_to_cart(self, shop: str, sku: str, qty: int) -> dict:
        return self.tools["agent"].call("add_to_cart", {"shop": shop, "sku": sku, "qty": qty})

    def mandate_id(self) -> str:
        return self.tools["agent"].mandate_id()

    def checkout(self, shop: str, signer: str = "agent") -> dict:
        t = self.tools[signer]
        t.call("checkout", {"shop": shop})
        self.last_request = t.last_request
        return t.routes[-1]

    def send(self, req: dict) -> dict:
        return self.tools["agent"].send(req)
