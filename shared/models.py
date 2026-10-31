"""Data contracts from spec §3. Strict models: no coercion, no unknown fields.

Strictness matters for signatures: a parsed model dumps back to exactly the dict that was signed.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


# ---------- Mandate (signed by the user's phone) ----------
class User(Strict):
    id: str
    name: str
    phone_pubkey: str


class Limits(Strict):
    per_order_paise: int
    per_week_paise: int


class IntentItem(Strict):
    family: str
    max_qty: int
    brands: list[str]
    substitutes_ok: bool


class Intent(Strict):
    items: list[IntentItem]


class StepUp(Strict):
    new_brand: bool
    order_over_pct_of_cap: int


class Mandate(Strict):
    mandate_id: str
    user: User
    agent_pubkey: str
    reserve_block_id: str
    allowed_merchants: list[str]
    allowed_categories: list[str]
    limits: Limits
    intent: Intent
    price_band_pct: int
    step_up: StepUp
    valid_from: str
    valid_until: str
    signature: str


# ---------- PaymentRequest (signed by the agent) ----------
class CartItem(Strict):
    sku: str
    family: str
    brand: str
    category: str
    qty: int
    claimed_unit_price_paise: int


class PaymentRequest(Strict):
    request_id: str
    mandate_id: str
    merchant: str
    cart: list[CartItem]
    claimed_total_paise: int
    nonce: str
    created_at: str
    agent_pubkey: str
    signature: str


# ---------- Decision (produced by the gateway) ----------
Outcome = Literal["ALLOWED", "BLOCKED", "HELD"]

# Decision fields not covered by the gateway signature (added after the log append).
DECISION_UNSIGNED_FIELDS = ("gateway_signature", "log_index", "log_hash")

EVENT_TYPES = {
    "agent.thought", "agent.tool_call", "agent.tool_result", "shop.page_viewed",
    "request.created", "gateway.check", "gateway.decision", "rail.debit", "rail.balance",
    "mandate.signed", "mandate.revoked", "stepup.requested", "stepup.resolved",
    "log.appended", "log.tampered", "director.moment", "system.mode", "score.update", "eval.row", "eval.status",
}
LANES = {"left", "right", "both", "system"}
