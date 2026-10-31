"""Formal exposure analysis: the most a fully hijacked agent can take, proven with Z3.

The mandate and each defence's checks become linear integer constraints over a symbolic adversary
that controls the agent completely: any number of orders, any shop, any items, any quantities,
any claimed prices. It cannot forge Asha's or the gateway's signatures, and each order needs a
fresh nonce (so orders are distinct). Z3's optimiser then maximises four kinds of loss:

  total        everything that leaves the wallet
  wrong_shop   money paid to a shop not in the mandate (look-alikes included)
  off_list     money paid for things not on Asha's list
  overpay      money paid above the gateway's reference price for what was bought

The optimum is proven: Z3 returns it only once no better assignment exists. The model is a model
of the checks, not the Python code itself; tests/test_formal.py cross-checks the two on random
requests. This runs when a mandate is analysed, never on the payment path.
"""
import hashlib
import json
import time
from functools import lru_cache

from gateway.catalog import load as load_catalog
from shared.canonical import canonical_json

PROFILES = ("none", "rails", "leash")
OBJECTIVES = ("total", "wrong_shop", "off_list", "overpay")
QTY_MAX = 999          # shops refuse bigger carts
OTHER = "__other__"    # anything outside the gateway's catalogue (unknown SKU, made-up product)


def _products(mandate: dict) -> dict[str, dict]:
    cat = load_catalog()
    prods = {k: dict(v) for k, v in cat.items()}
    # An off-catalogue item the adversary can invent: claims an allowed category, has no reference
    # price (value 0 to Asha), and no family on her list.
    prods[OTHER] = {"name": "made-up item", "family": OTHER, "brand": "-",
                    "category": (mandate["allowed_categories"] or ["?"])[0], "price_paise": 0}
    return prods


def _allowed_in_intent(p: dict, mandate: dict, catalog: dict) -> bool:
    for it in mandate["intent"]["items"]:
        if it["family"] == p["family"]:
            if p["brand"] in it["brands"]:
                return True
            fam_brands = {q["brand"] for q in catalog.values() if q["family"] == p["family"]}
            return it["substitutes_ok"] and p["brand"] in fam_brands
    return False


def _build(z3, mandate: dict, profile: str, block_paise: int, n_orders: int):
    """Constraints for `n_orders` symbolic orders under `profile`. Returns (solver, terms, witness vars)."""
    cat = load_catalog()
    prods = _products(mandate)
    cap = mandate["limits"]["per_order_paise"]
    week = mandate["limits"]["per_week_paise"]
    band = mandate["price_band_pct"]
    max_qty = {i["family"]: i["max_qty"] for i in mandate["intent"]["items"]}
    big = block_paise  # nothing can exceed the reserve block (the rail enforces it)

    opt = z3.Optimize()
    orders = []
    # Products a check forces to zero get no variables at all (smaller search, same optimum).
    def possible(k: str, p: dict) -> bool:
        if profile in ("rails", "leash") and p["category"] not in mandate["allowed_categories"]:
            return False
        return not (profile == "leash" and (k == OTHER or not _allowed_in_intent(p, mandate, cat)))
    live = {k: p for k, p in prods.items() if possible(k, p)}
    prev_counted = None
    total = wrong = offl = over = budget = z3.IntVal(0)
    for i in range(n_orders):
        wrong_i = z3.Bool(f"wrong_shop_{i}")          # paid to a shop outside the mandate?
        qty = {k: (z3.Int(f"qty_{i}_{k}") if k in live else z3.IntVal(0)) for k in prods}
        spend = {k: (z3.Int(f"spend_{i}_{k}") if k in live else z3.IntVal(0)) for k in prods}  # money paid for k
        for k, p in live.items():
            # checks 2 (category) and 4 (intent) already removed the products they forbid
            fam_cap = max_qty.get(p["family"], QTY_MAX) if profile == "leash" else QTY_MAX
            opt.add(qty[k] >= 0, qty[k] <= fam_cap, spend[k] >= 0, spend[k] <= qty[k] * big)
            if profile == "leash":
                opt.add(spend[k] * 100 <= qty[k] * p["price_paise"] * (100 + band))  # check 5
        order_spend = z3.Sum(list(spend.values()))
        order_value = z3.Sum([qty[k] * prods[k]["price_paise"] for k in prods])
        # Check 3 counts max(reference value, claimed spend), so an under-priced order still uses budget.
        counted = z3.Int(f"counted_{i}")
        opt.add(counted >= order_spend, counted >= order_value)
        if prev_counted is not None:   # orders are interchangeable: list them largest first
            opt.add(prev_counted >= order_spend)
        prev_counted = order_spend
        if profile in ("rails", "leash"):
            opt.add(order_spend <= cap, order_value <= cap)          # check 3 (per order)
        if profile == "leash":
            opt.add(z3.Not(wrong_i))                                  # check 2 (exact merchant)
            for fam, mx in max_qty.items():                           # check 4 (quantities)
                fam_q = [qty[k] for k, p in live.items() if p["family"] == fam]
                if fam_q:
                    opt.add(z3.Sum(fam_q) <= mx)
        w_i = z3.Int(f"wrong_amt_{i}")
        opt.add(w_i >= 0, w_i <= order_spend, z3.Implies(z3.Not(wrong_i), w_i == 0),
                z3.Implies(wrong_i, w_i == order_spend))
        off_terms = [spend[k] for k, p in live.items() if k == OTHER or not _allowed_in_intent(p, mandate, cat)]
        total = total + order_spend
        budget = budget + counted
        wrong = wrong + w_i
        offl = offl + (z3.Sum(off_terms) if off_terms else z3.IntVal(0))
        over = over + (order_spend - order_value)
        orders.append({"wrong": wrong_i, "qty": qty, "spend": spend})
    if profile in ("rails", "leash"):
        opt.add(budget <= week, budget <= block_paise)                # check 3 (week, reserve block)
    opt.add(total <= block_paise)                                     # the rail itself
    return opt, {"total": total, "wrong_shop": wrong, "off_list": offl, "overpay": over,
                 "budget": budget}, orders, prods


def _n_orders(mandate: dict, profile: str, block: int) -> int:
    if profile == "none":
        return 1  # no per-order cap: one order can take the whole block
    budget = min(mandate["limits"]["per_week_paise"], block)
    return budget // max(1, mandate["limits"]["per_order_paise"]) + 1


def _witness(z3, model, orders, prods, mandate) -> list[dict]:
    plan = []
    for o in orders:
        items = []
        for k, p in prods.items():
            q = model.eval(o["qty"][k], model_completion=True).as_long()
            s = model.eval(o["spend"][k], model_completion=True).as_long()
            if q and s:
                items.append({"product": p["name"], "qty": q, "paid_paise": s,
                              "reference_paise": q * p["price_paise"]})
        if items:
            wrong = z3.is_true(model.eval(o["wrong"], model_completion=True))
            plan.append({"shop": "a shop outside the mandate" if wrong else " / ".join(mandate["allowed_merchants"]),
                         "items": items, "paid_paise": sum(i["paid_paise"] for i in items)})
    return plan


def _solve(mandate: dict, profile: str, objective: str, block: int) -> dict:
    import z3
    opt, terms, orders, prods = _build(z3, mandate, profile, block, _n_orders(mandate, profile, block))
    h = opt.maximize(terms[objective])
    t0 = time.perf_counter()
    res = opt.check()
    ms = int((time.perf_counter() - t0) * 1000)
    if res != z3.sat:
        return {"value_paise": None, "status": str(res), "ms": ms}
    value = opt.upper(h).as_long() if hasattr(opt.upper(h), "as_long") else int(str(opt.upper(h)))
    out = {"value_paise": value, "status": "optimal", "ms": ms}
    if objective == "total" or value:
        out["witness"] = _witness(z3, opt.model(), orders, prods, mandate)
    return out


@lru_cache(maxsize=64)
def _analyse_cached(key: str, mandate_json: str, block: int, profiles: tuple[str, ...]) -> dict:
    mandate = json.loads(mandate_json)
    t0 = time.perf_counter()
    result = {p: ({o: _solve(mandate, p, o, block) for o in OBJECTIVES} if p != "none"
                  else {"total": _solve(mandate, p, "total", block)} if profiles != PROFILES
                  else {o: _solve(mandate, p, o, block) for o in OBJECTIVES}) for p in profiles}
    return {"profiles": result, "block_paise": block, "solver": "z3", "ms": int((time.perf_counter() - t0) * 1000),
            "mandate_hash": key}


def analyse(mandate: dict, block_paise: int, profiles: tuple[str, ...] = PROFILES) -> dict:
    """Worst-case exposure of Asha's wallet under each defence, for this mandate."""
    profiles = tuple(p for p in PROFILES if p in profiles)
    body = {k: v for k, v in mandate.items() if k not in ("signature", "mandate_id", "valid_from", "valid_until")}
    mj = canonical_json(body).decode()
    key = hashlib.sha256(mj.encode() + str(block_paise).encode()).hexdigest()[:16]
    return _analyse_cached(key, mj, block_paise, profiles)


def accepts(mandate: dict, cart: list[dict], merchant: str, week_spent_paise: int, block_paise: int) -> bool:
    """Does the formal model (leash) accept this concrete order? Used to cross-check the Python checks."""
    import z3
    cat = load_catalog()
    from gateway.catalog import product_key
    opt, terms, orders, prods = _build(z3, mandate, "leash", block_paise - week_spent_paise, 1)
    s = z3.Solver()
    s.add(opt.assertions())
    o = orders[0]
    s.add(o["wrong"] == (merchant not in mandate["allowed_merchants"]))
    by_key: dict[str, list[int]] = {}
    for it in cart:
        k = product_key(it["sku"])
        k = k if k in cat else OTHER
        q, s_ = by_key.get(k, [0, 0])
        by_key[k] = [q + it["qty"], s_ + it["qty"] * it["claimed_unit_price_paise"]]
    for k in prods:
        q, sp = by_key.get(k, [0, 0])
        s.add(o["qty"][k] == q, o["spend"][k] == sp)
    # the week cap applies to this order plus what was already spent (as check 3 counts it)
    s.add(terms["budget"] + week_spent_paise <= mandate["limits"]["per_week_paise"])
    return s.check() == z3.sat
