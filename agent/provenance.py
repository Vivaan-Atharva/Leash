"""Provenance ledger: where did each value in a payment request come from?

The agent runtime records every piece of text the model has read, labelled TRUSTED (the user's
task) or UNTRUSTED (shop pages, with how each piece was hidden from a human). Each tool-call
argument and each payment-request field is traced back to the source it appears in, in the spirit
of CaMeL's capabilities and FIDES's integrity labels.

This is attribution, not enforcement. It runs inside the (untrusted) agent runtime and matches
values to text, so it explains an attack but never decides one. The gateway's six checks decide.
"""
import re

NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
             8: "eight", 9: "nine", 10: "ten", 12: "twelve", 20: "twenty", 40: "forty"}
SHOP_ALIASES = {"freshcart": ["freshcart.in", "FreshCart"], "dailybasket": ["dailybasket.in", "DailyBasket"],
                "freshkart": ["fresh-kart.in", "FreshKart"]}
# Which gateway checks govern which request field (to point at the culprit).
FIELD_CHECKS = {"merchant": [2], "sku": [2, 4], "qty": [3, 4], "price": [5, 3]}


def _needles(value) -> list[re.Pattern]:
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        # whole number only: not part of 400, 4.0, ₹40 or 40%, but a sentence-ending "40." counts
        pats = [re.compile(rf"(?<![\d₹])(?<!\d[.,]){value}(?!\d|[.,]\d|%)")]
        if value in NUM_WORDS:
            pats.append(re.compile(rf"\b{NUM_WORDS[value]}\b", re.I))
        return pats
    s = str(value).strip()
    if not s:
        return []
    forms = [s] + SHOP_ALIASES.get(s.lower(), [])
    return [re.compile(re.escape(f), re.I) for f in dict.fromkeys(forms)]


class Ledger:
    def __init__(self):
        self.sources: list[dict] = []
        self.calls: list[dict] = []
        self.last_thought: str | None = None
        self.last_page: dict | None = None

    # ---- what the model has read -----------------------------------------
    def add_task(self, text: str) -> None:
        self.sources.append({"id": len(self.sources), "trusted": True, "kind": "task", "url": None,
                             "hidden": None, "text": text})

    def add_page(self, url: str, merchant: str, segments: list[dict]) -> None:
        ids = []
        for seg in segments:
            ids.append(len(self.sources))
            self.sources.append({"id": len(self.sources), "trusted": False, "kind": "page", "url": url,
                                 "merchant": merchant, "hidden": seg["hidden"], "text": seg["text"]})
        self.last_page = {"url": url, "merchant": merchant, "source_ids": ids}

    def note_thought(self, text: str) -> None:
        self.last_thought = text

    # ---- tracing ---------------------------------------------------------
    def find(self, value) -> dict:
        """Trusted sources first, then hidden page text, then visible page text (newest first)."""
        pats = _needles(value)
        trusted = [s for s in self.sources if s["trusted"]]
        hidden = [s for s in reversed(self.sources) if not s["trusted"] and s["hidden"]]
        visible = [s for s in reversed(self.sources) if not s["trusted"] and not s["hidden"]]
        for group in (trusted, hidden, visible):
            for s in group:
                for p in pats:
                    m = p.search(s["text"])
                    if m:
                        a, b = m.span()
                        return {
                            "label": "trusted" if s["trusted"] else "untrusted",
                            "how": "your task" if s["trusted"] else (s["hidden"] or "visible page text"),
                            "hidden": bool(s.get("hidden")), "url": s["url"], "source_id": s["id"],
                            "excerpt": {"before": s["text"][max(0, a - 90):a], "match": s["text"][a:b],
                                        "after": s["text"][b:b + 90]},
                        }
        return {"label": "unsourced", "how": "not found in anything the model read", "hidden": False,
                "url": None, "source_id": None, "excerpt": None}

    def note_call(self, tool: str, args: dict) -> int:
        prov = {}
        for k in ("qty", "sku", "shop", "url"):
            if k in args:
                v = args[k]
                if k == "qty":
                    try:
                        v = int(v)
                    except (TypeError, ValueError):
                        pass
                prov[k] = self.find(v)
        self.calls.append({"tool": tool, "args": args, "thought": self.last_thought, "prov": prov})
        return len(self.calls) - 1

    def _call_for_sku(self, sku: str) -> dict | None:
        return next((c for c in reversed(self.calls) if c["tool"] == "add_to_cart" and c["args"].get("sku") == sku), None)

    def request_fields(self, req: dict) -> list[dict]:
        fields = []
        first_add = next((c for c in self.calls if c["tool"] == "add_to_cart"), None)
        fields.append({"path": "merchant", "field": "merchant", "value": req["merchant"],
                       "display": req["merchant"], "checks": FIELD_CHECKS["merchant"],
                       "prov": self.find(req["merchant"]), "call": first_add})
        for i, it in enumerate(req["cart"]):
            call = self._call_for_sku(it["sku"])
            fields.append({"path": f"cart[{i}].sku", "field": "sku", "value": it["sku"],
                           "display": f"{it['brand']} {it['family']} ({it['sku']})", "checks": FIELD_CHECKS["sku"],
                           "prov": self.find(it["sku"]), "call": call})
            qprov = (call or {}).get("prov", {}).get("qty") or self.find(it["qty"])
            fields.append({"path": f"cart[{i}].qty", "field": "qty", "value": it["qty"], "display": f"×{it['qty']}",
                           "checks": FIELD_CHECKS["qty"], "prov": qprov, "call": call})
            fields.append({"path": f"cart[{i}].claimed_unit_price_paise", "field": "price",
                           "value": it["claimed_unit_price_paise"], "display": f"₹{it['claimed_unit_price_paise'] // 100}",
                           "checks": FIELD_CHECKS["price"],
                           "prov": {"label": "untrusted", "how": "price set by the shop", "hidden": False,
                                    "url": (self.last_page or {}).get("url"), "source_id": None, "excerpt": None},
                           "call": call})
        return fields


def pick_culprit(fields: list[dict], failing: list[int]) -> int | None:
    """The field to follow on screen: one a failing check governs, preferring hidden-text sources."""
    fail = set(failing)
    ranked = [
        lambda f: fail & set(f["checks"]) and f["prov"]["hidden"],
        lambda f: fail & set(f["checks"]) and f["prov"]["label"] == "untrusted" and f["field"] != "sku",
        lambda f: fail & set(f["checks"]),
        lambda f: f["prov"]["hidden"],
    ]
    for rule in ranked:
        for i, f in enumerate(fields):
            if rule(f):
                return i
    return None


def page_view(ledger: Ledger, sources_limit: int = 30) -> dict | None:
    if not ledger.last_page:
        return None
    segs = [ledger.sources[i] for i in ledger.last_page["source_ids"]][:sources_limit]
    return {"url": ledger.last_page["url"], "merchant": ledger.last_page["merchant"],
            "segments": [{"id": s["id"], "text": s["text"][:280], "hidden": s["hidden"]} for s in segs]}
