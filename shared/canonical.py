"""Canonical JSON: sorted keys, no whitespace, UTF-8. Floats are refused (money is paise)."""
import json
from typing import Any


def _reject_floats(obj: Any) -> None:
    if isinstance(obj, float):
        raise TypeError(f"floats are not allowed in signed objects: {obj!r}")
    if isinstance(obj, dict):
        for v in obj.values():
            _reject_floats(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _reject_floats(v)


def canonical_json(obj: Any) -> bytes:
    _reject_floats(obj)
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
