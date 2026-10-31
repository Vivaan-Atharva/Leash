"""Asha's seed mandate (spec §3.1 / §5). Numbers match the deck: ₹150/order, ₹500/week."""
from datetime import timedelta

from shared.crypto import sign_obj
from shared.keys import public_key, signing_key
from shared.timeutil import iso, utcnow

SEED_MANDATE_ID = "mdt_7f3a"
RIGHT_BLOCK_ID = "blk_r_01"
LEFT_BLOCK_ID = "blk_l_01"


def mandate_body(phone_pubkey: str, agent_pubkey: str, mandate_id: str = SEED_MANDATE_ID) -> dict:
    now = utcnow()
    return {
        "mandate_id": mandate_id,
        "user": {"id": "usr_asha", "name": "Asha", "phone_pubkey": phone_pubkey},
        "agent_pubkey": agent_pubkey,
        "reserve_block_id": RIGHT_BLOCK_ID,
        "allowed_merchants": ["freshcart.in", "dailybasket.in"],
        "allowed_categories": ["dairy", "bakery", "staples"],
        "limits": {"per_order_paise": 15000, "per_week_paise": 50000},
        "intent": {"items": [
            {"family": "milk", "max_qty": 2, "brands": ["Amul", "Nandini"], "substitutes_ok": True},
            {"family": "bread", "max_qty": 1, "brands": ["Modern", "Britannia"], "substitutes_ok": True},
            {"family": "butter", "max_qty": 1, "brands": ["Amul"], "substitutes_ok": False},
        ]},
        "price_band_pct": 15,
        "step_up": {"new_brand": True, "order_over_pct_of_cap": 70},
        # Rolling window so the demo works whenever it runs; same one-week length as the deck.
        "valid_from": iso(now - timedelta(hours=1)),
        "valid_until": iso(now + timedelta(days=7)),
    }


def seed_mandate() -> dict:
    body = mandate_body(public_key("phone"), public_key("agent"))
    return sign_obj(body, signing_key("phone"))
