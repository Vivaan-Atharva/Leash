"""The six checks (spec §4). Pure functions: same request + mandate + state = same result.

No I/O, no clock reads, no randomness, and never an LLM.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from gateway.catalog import brands_for_family, product_key
from shared.crypto import verify_obj
from shared.models import Mandate, PaymentRequest
from shared.money import inr
from shared.timeutil import parse

MAX_REQUEST_AGE = timedelta(seconds=120)
IST = timezone(timedelta(hours=5, minutes=30))  # display only; decisions never depend on it


@dataclass(frozen=True)
class State:
    now: datetime
    registered_agents: frozenset[str]
    revoked_at: str | None
    nonce_seen: bool
    week_spent_paise: int
    block_remaining_paise: int
    catalog: dict  # product_key -> reference entry


@dataclass(frozen=True)
class CheckResult:
    n: int
    name: str
    passed: bool
    detail: str

    def wire(self) -> dict:
        return {"n": self.n, "name": self.name, "pass": self.passed, "detail": self.detail}


def _ref(state: State, sku: str) -> dict | None:
    return state.catalog.get(product_key(sku))


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------- 1. identity
def check_1(req: PaymentRequest, m: Mandate, s: State) -> CheckResult:
    problems = []
    if req.agent_pubkey != m.agent_pubkey:
        problems.append("agent key not in mandate")
    if req.agent_pubkey not in s.registered_agents:
        problems.append("unknown agent key")
    if not verify_obj(req.model_dump(mode="json"), req.agent_pubkey):
        problems.append("bad signature")
    if problems:
        return CheckResult(1, "identity", False, "; ".join(problems))
    return CheckResult(1, "identity", True, "agent key registered, signature valid")


# ---------------------------------------------------------------- 2. merchant
def _category(s: State, item) -> str:
    ref = _ref(s, item.sku)
    return ref["category"] if ref else item.category


def _category_problems(req: PaymentRequest, m: Mandate, s: State) -> list[str]:
    bad = sorted({_category(s, it) for it in req.cart} - set(m.allowed_categories))
    return [f"category {c} not in mandate" for c in bad]


def check_2(req: PaymentRequest, m: Mandate, s: State) -> CheckResult:
    problems = []
    if req.merchant not in m.allowed_merchants:  # exact match only
        close = [a for a in m.allowed_merchants if levenshtein(req.merchant, a) <= 2]
        hint = f" (look-alike of {close[0]})" if close else ""
        problems.append(f"{req.merchant} not in mandate{hint}")
    problems += _category_problems(req, m, s)
    if problems:
        return CheckResult(2, "merchant", False, "; ".join(problems))
    return CheckResult(2, "merchant", True, f"{req.merchant} in mandate")


def check_2_category_only(req: PaymentRequest, m: Mandate, s: State) -> CheckResult:
    """What today's rails do: merchant category is checked, merchant identity is not."""
    problems = _category_problems(req, m, s)
    if problems:
        return CheckResult(2, "merchant", False, "; ".join(problems))
    return CheckResult(2, "merchant", True, "merchant category allowed (identity not checked)")


# ---------------------------------------------------------------- 3. limits
def order_total_paise(req: PaymentRequest, s: State) -> int:
    """Total used for limits: never trust the shop's total to be the low one."""
    ref_total = 0
    for it in req.cart:
        ref = _ref(s, it.sku)
        unit = ref["price_paise"] if ref else it.claimed_unit_price_paise
        ref_total += unit * it.qty
    line_total = sum(it.claimed_unit_price_paise * it.qty for it in req.cart)
    return max(ref_total, line_total, req.claimed_total_paise)


def check_3(req: PaymentRequest, m: Mandate, s: State) -> CheckResult:
    total = order_total_paise(req, s)
    cap, week_cap = m.limits.per_order_paise, m.limits.per_week_paise
    week_after = s.week_spent_paise + total
    problems = []
    if total > cap:
        problems.append(f"{inr(total)} > {inr(cap)} per order")
    if week_after > week_cap:
        problems.append(f"week {inr(week_after)} > {inr(week_cap)} weekly cap")
    if total > s.block_remaining_paise:
        problems.append(f"{inr(total)} > {inr(s.block_remaining_paise)} left in reserve block")
    if problems:
        return CheckResult(3, "limits", False, "; ".join(problems))
    return CheckResult(3, "limits", True,
                       f"{inr(total)} ≤ {inr(cap)} per order; week {inr(week_after)}/{inr(week_cap)}")


# ---------------------------------------------------------------- 4. intent
def check_4(req: PaymentRequest, m: Mandate, s: State) -> CheckResult:
    wanted = {i.family: i for i in m.intent.items}
    problems, ok_parts = [], []
    qty_by_family: dict[str, int] = {}
    for it in req.cart:
        ref = _ref(s, it.sku)
        if ref is None:
            problems.append(f"unknown product {it.sku}")
            continue
        if (it.family, it.brand, it.category) != (ref["family"], ref["brand"], ref["category"]):
            problems.append(f"{it.sku} metadata doesn't match catalogue")
        if it.qty < 1:
            problems.append(f"{it.sku} qty {it.qty} invalid")
        family = ref["family"]
        rule = wanted.get(family)
        if rule is None:
            problems.append(f"{family} not in intent")
            continue
        qty_by_family[family] = qty_by_family.get(family, 0) + it.qty
        brand = ref["brand"]
        if brand not in rule.brands and not (
            rule.substitutes_ok and brand in brands_for_family(s.catalog, family)
        ):
            problems.append(f"{family} brand {brand} not allowed")
    for family, qty in qty_by_family.items():
        mx = wanted[family].max_qty
        if qty > mx:
            problems.append(f"{family} ×{qty} > max {mx}")
        else:
            ok_parts.append(f"{family} ×{qty} ≤ {mx}")
    if not req.cart:
        problems.append("empty cart")
    if problems:
        return CheckResult(4, "intent", False, "; ".join(problems))
    return CheckResult(4, "intent", True, "; ".join(ok_parts))


# ---------------------------------------------------------------- 5. price
def check_5(req: PaymentRequest, m: Mandate, s: State) -> CheckResult:
    band = m.price_band_pct
    problems = []
    for it in req.cart:
        ref = _ref(s, it.sku)
        claimed = it.claimed_unit_price_paise
        if ref is None:
            problems.append(f"no reference price for {it.sku}")
            continue
        rp = ref["price_paise"]
        if claimed < 0:
            problems.append(f"{it.sku} negative price")
        elif claimed * 100 > rp * (100 + band):
            pct = (claimed - rp) * 100 // rp
            problems.append(f"{inr(claimed)} vs reference {inr(rp)} (+{pct}%) > ±{band}%")
    line_total = sum(it.claimed_unit_price_paise * it.qty for it in req.cart)
    if line_total != req.claimed_total_paise:
        problems.append(f"claimed total {inr(req.claimed_total_paise)} ≠ items {inr(line_total)}")
    if problems:
        return CheckResult(5, "price", False, "; ".join(problems))
    return CheckResult(5, "price", True, f"all items within ±{band}% of reference")


# ---------------------------------------------------------------- 6. validity
def check_6(req: PaymentRequest, m: Mandate, s: State) -> CheckResult:
    problems = []
    if not (parse(m.valid_from) <= s.now < parse(m.valid_until)):
        problems.append("mandate not active now")
    if s.revoked_at:
        problems.append(f"mandate revoked at {parse(s.revoked_at).astimezone(IST):%H:%M:%S} IST")
    if s.nonce_seen:
        problems.append("replayed nonce")
    try:
        age = abs(s.now - parse(req.created_at))
        if age > MAX_REQUEST_AGE:
            problems.append(f"request is {int(age.total_seconds())} s old (max 120 s)")
    except ValueError:
        problems.append("bad created_at")
    if problems:
        return CheckResult(6, "validity", False, "; ".join(problems))
    return CheckResult(6, "validity", True, "active, not revoked, nonce fresh")


# ---------------------------------------------------------------- profiles
PROFILES = {
    "none": [],
    "rails": [check_1, check_2_category_only, check_3, check_6],
    "leash": [check_1, check_2, check_3, check_4, check_5, check_6],
}
NAMES = {1: "identity", 2: "merchant", 3: "limits", 4: "intent", 5: "price", 6: "validity"}


def run_checks(profile: str, req: PaymentRequest | None, m: Mandate | None,
               s: State) -> list[CheckResult]:
    """Run every check in the profile. Never stops at the first failure."""
    fns = PROFILES[profile]
    if req is None or m is None:
        why = "malformed request" if req is None else "unknown mandate"
        nums = [1, 2, 3, 6] if profile == "rails" else ([] if profile == "none" else range(1, 7))
        return [CheckResult(n, NAMES[n], False, why) for n in nums] or [
            CheckResult(1, "identity", False, why)]
    return [fn(req, m, s) for fn in fns]


def outcome(results: list[CheckResult]) -> str:
    return "ALLOWED" if all(r.passed for r in results) else "BLOCKED"


# ---------------------------------------------------------------- step-up (Phase 3)
def step_up_reason(req: PaymentRequest, m: Mandate, s: State, known_brands: frozenset) -> str | None:
    """After all six pass: should Asha approve this on her phone first?

    known_brands: (family, brand) pairs Asha already buys: the first brand of each mandate item
    (her usual) plus every brand bought under this mandate.
    """
    reasons = []
    if m.step_up.new_brand:
        for it in req.cart:
            ref = _ref(s, it.sku)
            if ref and (ref["family"], ref["brand"]) not in known_brands:
                reasons.append(f"new brand: {ref['brand']} {ref['family']}")
    total = order_total_paise(req, s)
    threshold = m.limits.per_order_paise * m.step_up.order_over_pct_of_cap // 100
    if total > threshold:
        reasons.append(f"{inr(total)} is over {m.step_up.order_over_pct_of_cap}% of the per-order cap")
    return "; ".join(dict.fromkeys(reasons)) or None


def usual_brands(m: Mandate) -> set[tuple[str, str]]:
    return {(i.family, i.brands[0]) for i in m.intent.items if i.brands}
