"""Each of the six checks: the pass case and every failure mode."""
from gateway import checks as C
from tests.helpers import iso, item, mandate, request, state, timedelta, utcnow

M = mandate()


def failing(req, st=None, profile="leash"):
    return [r.n for r in C.run_checks(profile, req, M, st or state()) if not r.passed]


def test_honest_purchase_passes_all_six():
    res = C.run_checks("leash", request(), M, state())
    assert [r.n for r in res] == [1, 2, 3, 4, 5, 6]
    assert all(r.passed for r in res)
    assert C.outcome(res) == "ALLOWED"


def test_all_checks_run_even_after_a_failure():
    res = C.run_checks("leash", request(cart=[item("FC-BUTTER-AMUL-100", 40)]), M, state())
    assert len(res) == 6 and [r.n for r in res if not r.passed] == [3, 4]


def test_deterministic():
    req, st = request(), state()
    assert C.run_checks("leash", req, M, st) == C.run_checks("leash", req, M, st)


# 1 identity
def test_identity_unregistered_key():
    r = C.check_1(request(signer="rogue"), M, state())
    assert not r.passed and "unknown agent key" in r.detail


def test_identity_bad_signature():
    req = request()
    tampered = req.model_copy(update={"claimed_total_paise": 1})
    r = C.check_1(tampered, M, state())
    assert not r.passed and "bad signature" in r.detail


def test_identity_registered_but_not_mandate_key():
    from shared.keys import public_key
    r = C.check_1(request(signer="rogue"), M,
                  state(registered_agents=frozenset({public_key("agent"), public_key("rogue")})))
    assert not r.passed and "not in mandate" in r.detail


# 2 merchant
def test_merchant_lookalike():
    r = C.check_2(request(merchant="fresh-kart.in"), M, state())
    assert not r.passed and "look-alike of freshcart.in" in r.detail


def test_merchant_unrelated_no_lookalike_hint():
    r = C.check_2(request(merchant="evil.example"), M, state())
    assert not r.passed and "look-alike" not in r.detail


def test_merchant_category_not_allowed():
    r = C.check_2(request(cart=[item("FC-GIFT-LOYALTY-100")]), M, state())
    assert not r.passed and "gift_card" in r.detail


def test_rails_profile_ignores_merchant_identity():
    assert failing(request(merchant="fresh-kart.in"), profile="rails") == []
    assert failing(request(cart=[item("FC-GIFT-LOYALTY-100")]), profile="rails") == [2]


# 3 limits
def test_limits_per_order():
    r = C.check_3(request(cart=[item("FC-BUTTER-AMUL-100", 40)]), M, state())
    assert not r.passed and "₹3,960 > ₹150 per order" in r.detail


def test_limits_weekly():
    r = C.check_3(request(cart=[item("FC-BUTTER-AMUL-100")]), M, state(week_spent_paise=49500))
    assert not r.passed and "weekly cap" in r.detail


def test_limits_reserve_block():
    r = C.check_3(request(), M, state(block_remaining_paise=5000))
    assert not r.passed and "reserve block" in r.detail


def test_limits_use_reference_not_shop_total():
    # shop claims a tiny price; limits still use the reference price (40 × ₹99)
    req = request(cart=[item("FC-BUTTER-AMUL-100", 40, price=1)])
    assert not C.check_3(req, M, state()).passed


# 4 intent
def test_intent_family_not_in_intent():
    r = C.check_4(request(cart=[item("FC-GIFT-LOYALTY-100")]), M, state())
    assert not r.passed and "gift_card not in intent" in r.detail


def test_intent_qty_over_max_across_lines():
    r = C.check_4(request(cart=[item(qty=2), item(qty=1)]), M, state())
    assert not r.passed and "milk ×3 > max 2" in r.detail


def test_intent_brand_substitute_rules():
    # bread: substitutes ok, Britannia listed; butter: no substitutes
    assert C.check_4(request(cart=[item("FC-BREAD-BRITANNIA-WW")]), M, state()).passed
    r = C.check_4(request(cart=[item("FC-BUTTER-AMUL-100", brand="Nandini")]), M, state())
    assert not r.passed


def test_intent_unknown_product_and_bad_qty():
    assert not C.check_4(request(cart=[item("FC-CAVIAR-1")]), M, state()).passed
    assert not C.check_4(request(cart=[item(qty=0)]), M, state()).passed
    assert not C.check_4(request(cart=[]), M, state()).passed


def test_intent_metadata_must_match_catalogue():
    r = C.check_4(request(cart=[item("FC-GIFT-LOYALTY-100", family="milk", category="dairy")]),
                  M, state())
    assert not r.passed and "metadata" in r.detail


# 5 price
def test_price_3x():
    r = C.check_5(request(cart=[item(price=13500)]), M, state())
    assert not r.passed and "₹135 vs reference ₹45 (+200%) > ±15%" in r.detail


def test_price_inside_band_passes():
    assert C.check_5(request(cart=[item(price=5175)]), M, state()).passed  # exactly +15%
    assert not C.check_5(request(cart=[item(price=5176)]), M, state()).passed


def test_price_total_mismatch():
    r = C.check_5(request(total=1), M, state())
    assert not r.passed and "claimed total" in r.detail


# 6 validity
def test_validity_revoked():
    r = C.check_6(request(), M, state(revoked_at="2026-10-31T11:14:02Z"))
    assert not r.passed and "revoked at 16:44:02 IST" in r.detail


def test_validity_replayed_nonce():
    r = C.check_6(request(), M, state(nonce_seen=True))
    assert not r.passed and "replayed nonce" in r.detail


def test_validity_stale_request():
    r = C.check_6(request(created_at=iso(utcnow() - timedelta(seconds=300))), M, state())
    assert not r.passed and "old" in r.detail


def test_validity_outside_window():
    r = C.check_6(request(), M, state(now=utcnow() + timedelta(days=30)))
    assert not r.passed and "not active" in r.detail


def test_unknown_mandate_blocks():
    res = C.run_checks("leash", request(), None, state())
    assert len(res) == 6 and not any(r.passed for r in res)


def test_lookalike_distance():
    assert C.levenshtein("fresh-kart.in", "freshcart.in") == 2
