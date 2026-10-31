"""Tests use their own keys, data dir and ports so they never touch a running dev stack."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="leash-test-")
os.environ["LEASH_DATA_DIR"] = os.path.join(_tmp, "data")
os.environ["LEASH_KEYS_DIR"] = os.path.join(_tmp, "keys")
for i, svc in enumerate(("HUB", "GATEWAY", "RAIL", "SHOPS")):
    os.environ[f"LEASH_PORT_{svc}"] = str(18000 + i)
    os.environ.pop(f"LEASH_{svc}_URL", None)

from shared.keys import ensure_keys  # noqa: E402

ensure_keys()
