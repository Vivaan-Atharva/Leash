"""Wallet R cannot be debited without a gateway signature."""
import pytest
from fastapi.testclient import TestClient

from rail.app import app
from shared.crypto import sign_obj
from shared.keys import signing_key
from tests.helpers import request


@pytest.fixture
def rail():
    c = TestClient(app)
    c.post("/demo/reset")
    return c


def agent_req():
    return request().model_dump(mode="json")


def gw_debit(sk_name="gateway", block_id="blk_r_01", amount=9600):
    return sign_obj({"debit_id": "dbt_1", "block_id": block_id, "amount_paise": amount,
                     "merchant": "freshcart.in", "request_id": "req_test", "decision_id": "dec_1",
                     "created_at": "2026-10-31T11:00:00Z"}, signing_key(sk_name))


def test_wallet_r_refuses_agent_signed_debit(rail):
    r = rail.post("/debit", json={"block_id": "blk_r_01", "authorizer": "agent", "request": agent_req()})
    assert r.status_code == 403
    assert rail.get("/blocks/blk_r_01").json()["remaining_paise"] == 500000


def test_wallet_r_refuses_debit_signed_by_other_key(rail):
    for name in ("agent", "phone", "rogue"):
        r = rail.post("/debit", json={"block_id": "blk_r_01", "authorizer": "gateway",
                                      "debit": gw_debit(name)})
        assert r.status_code == 403
    assert rail.get("/blocks/blk_r_01").json()["remaining_paise"] == 500000


def test_wallet_r_refuses_tampered_amount(rail):
    d = {**gw_debit(), "amount_paise": 400000}
    r = rail.post("/debit", json={"block_id": "blk_r_01", "authorizer": "gateway", "debit": d})
    assert r.status_code == 403


def test_wallet_r_accepts_gateway_signed_once(rail):
    body = {"block_id": "blk_r_01", "authorizer": "gateway", "debit": gw_debit()}
    assert rail.post("/debit", json=body).json()["balance_paise"] == 490400
    assert rail.post("/debit", json=body).status_code == 409  # same debit_id can't settle twice


def test_wallet_l_takes_any_agent_signed_request(rail):
    body = {"block_id": "blk_l_01", "authorizer": "agent", "request": agent_req()}
    assert rail.post("/debit", json=body).status_code == 200
    assert rail.post("/debit", json=body).status_code == 200  # replay pays twice on the left
    assert rail.get("/blocks/blk_l_01").json()["remaining_paise"] == 500000 - 2 * 9600


def test_revoke_rules(rail):
    assert rail.post("/blocks/blk_l_01/revoke", json={}).json()["detail"] == "revoke must go through merchant"
    assert rail.post("/blocks/blk_r_01/revoke", json={}).status_code == 401
    body = sign_obj({"block_id": "blk_r_01", "action": "revoke", "ts": "t"}, signing_key("gateway"))
    assert rail.post("/blocks/blk_r_01/revoke", json=body).status_code == 200
    r = rail.post("/debit", json={"block_id": "blk_r_01", "authorizer": "gateway", "debit": gw_debit()})
    assert r.status_code == 409
