"""End to end: real services as separate processes, scripted agent, S0–S9 vs spec §5."""
import httpx
import pytest

from agent import run_scenarios as R
from scripts.services import running
from shared.config import url


@pytest.fixture(scope="module")
def stack():
    with running():
        yield


def test_all_scenarios_match_spec(stack):
    results = R.run(R.ALL)
    by_id = {r["id"]: r for r in results}
    for r in results:
        assert r["ok"], r
    stage = [by_id[s] for s in R.STAGE if by_id[s]["attack"]]
    assert sum(r["left_paid_paise"] for r in stage) == 443100   # ₹4,431
    assert sum(r["right_paid_paise"] for r in stage) == 0       # ₹0


def test_decisions_are_fast_and_chain_verifies(stack):
    results = R.run(["S0", "S1"])
    for r in results:
        for d in r["right"]:
            assert d["decided_in_us"] < 10_000
    v = httpx.get(f"{url('gateway')}/log/verify").json()
    assert v["ok"] and v["length"] >= 3


def test_decision_signature_and_tamper_endpoints(stack):
    res = R.run(["S1"])[0]
    did = res["right"][0]["decision_id"]
    assert httpx.get(f"{url('gateway')}/decisions/{did}/verify").json()["signature_ok"]
    t = httpx.post(f"{url('gateway')}/demo/tamper", json={}).json()
    assert t["ok"] is False and t["broken_at"] == t["tampered_index"]
    assert httpx.post(f"{url('gateway')}/demo/restore").json()["ok"] is True


def test_preflight_green_after_reset(stack):
    httpx.post(f"{url('hub')}/demo/reset").raise_for_status()
    assert httpx.get(f"{url('hub')}/preflight").json()["ok"]


def test_agent_cannot_debit_wallet_r_through_any_path(stack):
    """Even skipping the gateway, the agent's own key can't move wallet R."""
    from tests.helpers import request
    req = request().model_dump(mode="json")
    r = httpx.post(f"{url('rail')}/debit", json={"block_id": "blk_r_01", "authorizer": "agent", "request": req})
    assert r.status_code == 403
