from datetime import timedelta

from gateway import catalog, seed
from gateway.checks import State
from shared.crypto import pubkey_b64, random_nonce, sign_obj
from shared.keys import public_key, signing_key
from shared.models import Mandate, PaymentRequest
from shared.timeutil import iso, utcnow

REF = catalog.load()


def mandate() -> Mandate:
    return Mandate.model_validate(seed.seed_mandate())


def item(sku="FC-MILK-AMUL-500", qty=1, price=None, **over):
    ref = REF[catalog.product_key(sku)] if catalog.product_key(sku) in REF else {}
    d = {"sku": sku, "family": ref.get("family", "x"), "brand": ref.get("brand", "x"),
         "category": ref.get("category", "x"), "qty": qty,
         "claimed_unit_price_paise": ref.get("price_paise", 100) if price is None else price}
    d.update(over)
    return d


def request(cart=None, merchant="freshcart.in", signer="agent", total=None, created_at=None,
            **over) -> PaymentRequest:
    cart = cart if cart is not None else [item(), item("FC-BREAD-MODERN-WW")]
    sk = signing_key(signer)
    d = {"request_id": "req_test", "mandate_id": seed.SEED_MANDATE_ID, "merchant": merchant,
         "cart": cart,
         "claimed_total_paise": total if total is not None else
         sum(i["qty"] * i["claimed_unit_price_paise"] for i in cart),
         "nonce": random_nonce(), "created_at": created_at or iso(utcnow()),
         "agent_pubkey": pubkey_b64(sk)}
    d.update(over)
    return PaymentRequest.model_validate(sign_obj(d, sk))


def state(**over) -> State:
    d = dict(now=utcnow(), registered_agents=frozenset({public_key("agent")}), revoked_at=None,
             nonce_seen=False, week_spent_paise=0, block_remaining_paise=500000, catalog=REF)
    d.update(over)
    return State(**d)


__all__ = ["mandate", "item", "request", "state", "timedelta", "iso", "utcnow"]
