import pytest

from shared.canonical import canonical_json
from shared.crypto import new_signing_key, pubkey_b64, sign_obj, verify_obj
from shared.money import inr


def test_canonical_sorted_compact_utf8():
    assert canonical_json({"b": 1, "a": {"d": "₹", "c": [2, 1]}}) == '{"a":{"c":[2,1],"d":"₹"},"b":1}'.encode()


def test_canonical_rejects_floats():
    with pytest.raises(TypeError):
        canonical_json({"amount": 45.0})


def test_sign_verify_roundtrip():
    sk = new_signing_key()
    obj = sign_obj({"z": 1, "a": "x"}, sk)
    assert verify_obj(obj, pubkey_b64(sk))
    # key order doesn't matter: canonical JSON sorts
    assert verify_obj(dict(reversed(list(obj.items()))), pubkey_b64(sk))


def test_verify_fails_on_change_or_wrong_key():
    sk = new_signing_key()
    obj = sign_obj({"amount_paise": 9600}, sk)
    assert not verify_obj({**obj, "amount_paise": 9601}, pubkey_b64(sk))
    assert not verify_obj(obj, pubkey_b64(new_signing_key()))
    assert not verify_obj({**obj, "signature": "not base64!"}, pubkey_b64(sk))


def test_money_format():
    assert inr(4500) == "₹45"
    assert inr(396000) == "₹3,960"
    assert inr(443100) == "₹4,431"
    assert inr(12345600) == "₹1,23,456"
    assert inr(4550) == "₹45.50"
    with pytest.raises(TypeError):
        inr(45.0)
