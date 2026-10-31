"""Step-up (held for phone approval) and the dispute report's verdicts."""
import httpx
import pytest

from agent import run_scenarios as R
from gateway import checks as C
from gateway.report import verdict
from scripts.services import running
from shared.config import url
from tests.helpers import item, mandate, request, state

M = mandate()
USUAL = frozenset(C.usual_brands(M))


def test_step_up_rules():
    assert C.step_up_reason(request(), M, state(), USUAL) is None               # usual milk + bread, ₹96
    assert "new brand: Nandini" in C.step_up_reason(request(cart=[item("FC-MILK-NANDINI-500")]), M, state(), USUAL)
    big = request(cart=[item(qty=1), item("FC-BREAD-MODERN-WW"), item("FC-MILK-AMUL-500", qty=1)])
    assert "over 70%" in C.step_up_reason(big, M, state(), USUAL)               # ₹141 > ₹105
    bought = USUAL | {("milk", "Nandini")}
    assert C.step_up_reason(request(cart=[item("FC-MILK-NANDINI-500")]), M, state(), frozenset(bought)) is None


def _dec(outcome, failing=(), amount=0, settlement_error=None):
    return {"outcome": outcome, "merchant": "freshcart.in", "amount_debited_paise": amount,
            "settlement_error": settlement_error,
            "checks": [{"n": n, "name": "x", "pass": n not in failing, "detail": ""} for n in range(1, 7)]}


def test_verdicts():
    assert verdict(_dec("BLOCKED", [3, 4]), None, None)["headline"] == \
        "Agent exceeded mandate (checks 3, 4). Blocked before settlement. User not liable."
    assert "not signed by Asha's registered agent" in verdict(_dec("BLOCKED", [1]), None, None)["headline"]
    assert "revoked the mandate" in verdict(_dec("BLOCKED", [6]), None, "2026-10-31T11:14:02Z")["headline"]
    assert verdict(_dec("ALLOWED", amount=9600), None, None)["liability"] == "Covered by the user's mandate"
    assert verdict(_dec("HELD"), None, None)["tone"] == "held"
    denied = {"outcome": "BLOCKED", "resolved_by": "timeout", "amount_debited_paise": 0, "error": None}
    assert "60 seconds" in verdict(_dec("HELD"), denied, None)["headline"]


@pytest.fixture(scope="module")
def stack():
    with running():
        yield


def test_s9_is_held_then_approved_on_phone(stack):
    http = httpx.Client(timeout=10)
    R.reset(http)
    res = R.run(["S9"])[0]
    assert res["ok"], res
    did = res["right"][0]["decision_id"]
    r = R.phone_approve(http, did, True)
    assert r["outcome"] == "ALLOWED" and r["amount_debited_paise"] == 4400
    assert http.get(f"{url('rail')}/wallets").json()["R"]["balance_paise"] == 500000 - 4400
    rep = http.get(f"{url('gateway')}/report/{did}").json()
    assert rep["verdict"]["tone"] == "allowed" and rep["signatures"]["resolution"] is True
    assert R.phone_approve(http, did, True).get("detail", "").startswith("already resolved")


def test_step_up_needs_phone_key(stack):
    http = httpx.Client(timeout=10)
    R.reset(http)
    did = R.run(["S9"])[0]["right"][0]["decision_id"]
    from shared.crypto import sign_obj
    from shared.keys import signing_key
    forged = sign_obj({"decision_id": did, "approve": True, "ts": "t"}, signing_key("agent"))
    assert http.post(f"{url('gateway')}/stepup/{did}", json=forged).status_code == 401
    assert R.phone_approve(http, did, False)["outcome"] == "BLOCKED"


def test_report_for_blocked_attack(stack):
    http = httpx.Client(timeout=10)
    R.reset(http)
    did = R.run(["S1"])[0]["right"][0]["decision_id"]
    rep = http.get(f"{url('gateway')}/report/{did}").json()
    assert rep["verdict"]["headline"] == "Agent exceeded mandate (checks 3, 4). Blocked before settlement. User not liable."
    assert all(rep["signatures"][k] for k in ("mandate", "request", "request_key_in_mandate", "decision"))
    assert rep["chain"]["ok"] and rep["chain"]["decision_entry_matches"]
    assert [t["type"] for t in rep["timeline"]] == ["MANDATE_SIGNED", "REQUEST", "DECISION"]
    http.post(f"{url('gateway')}/demo/tamper", json={"index": 1})
    rep = http.get(f"{url('gateway')}/report/{did}").json()
    assert rep["chain"]["ok"] is False and rep["chain"]["broken_at"] == 1
    http.post(f"{url('gateway')}/demo/restore")


def test_stepup_config_route_is_not_a_decision_id(stack):
    r = httpx.post(f"{url('gateway')}/stepup/config", json={"enabled": False})
    assert r.status_code == 200 and r.json() == {"enabled": False}
