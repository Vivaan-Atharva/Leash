"""Formal exposure model: the proven bounds, and agreement with the real Python checks."""
import random

import pytest

z3 = pytest.importorskip("z3")

from gateway import catalog, checks, formal  # noqa: E402
from tests.helpers import mandate, request, state  # noqa: E402

M = mandate()
MD = M.model_dump(mode="json")
BLOCK = 500000


def test_proven_bounds_for_asha():
    a = formal.analyse(MD, BLOCK)["profiles"]
    v = {p: {o: a[p][o]["value_paise"] for o in formal.OBJECTIVES} for p in formal.PROFILES}
    assert all(a[p][o]["status"] == "optimal" for p in formal.PROFILES for o in formal.OBJECTIVES)
    assert v["none"]["total"] == BLOCK                       # no protection: the whole block
    assert v["rails"]["total"] == v["leash"]["total"] == 50000  # spending caps bound both to ₹500/week
    assert v["leash"]["wrong_shop"] == 0 and v["leash"]["off_list"] == 0
    assert v["rails"]["wrong_shop"] == 50000 and v["rails"]["off_list"] == 50000
    assert 0 < v["leash"]["overpay"] <= 50000 * 15 // 115 + 100   # only the ±15% band
    assert v["rails"]["overpay"] > v["leash"]["overpay"] * 3
    w = a["leash"]["total"]["witness"]
    assert sum(o["paid_paise"] for o in w) == 50000 and all(o["paid_paise"] <= 15000 for o in w)


def test_model_agrees_with_python_checks_on_random_requests():
    """Differential test: for random orders, the Python checks pass all six iff the Z3 model accepts."""
    rng = random.Random(7)
    keys = list(catalog.load())
    merchants = MD["allowed_merchants"] + ["fresh-kart.in", "evil.example"]
    agree = 0
    for _ in range(250):
        lines = []
        for k in rng.sample(keys + ["CAVIAR-1"], rng.randint(1, 3)):
            ref = catalog.load().get(k, {"price_paise": 5000})
            lines.append({"sku": f"FC-{k}", "qty": rng.randint(1, 4),
                          "price": max(1, ref["price_paise"] * rng.randint(60, 200) // 100)})
        cart = []
        for ln in lines:
            ref = catalog.load().get(ln["sku"][3:])
            cart.append({"sku": ln["sku"], "family": ref["family"] if ref else "x", "brand": ref["brand"] if ref else "x",
                         "category": ref["category"] if ref else "dairy", "qty": ln["qty"],
                         "claimed_unit_price_paise": ln["price"]})
        merchant = rng.choice(merchants)
        week = rng.choice([0, 0, 20000, 45000])
        req = request(cart=cart, merchant=merchant)
        py = all(r.passed for r in checks.run_checks("leash", req, M, state(week_spent_paise=week,
                                                                               block_remaining_paise=BLOCK - week)))
        model = formal.accepts(MD, cart, merchant, week, BLOCK)
        assert py == model, (cart, merchant, week, py, model)
        agree += 1
    assert agree == 250
