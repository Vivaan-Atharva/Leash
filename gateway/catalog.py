import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).with_name("reference_catalog.json")


def product_key(sku: str) -> str:
    """'FC-MILK-AMUL-500' -> 'MILK-AMUL-500'. Shop prefixes differ; products don't."""
    return sku.split("-", 1)[1] if "-" in sku else sku


@lru_cache(maxsize=1)
def load() -> dict[str, dict]:
    return json.loads(PATH.read_text())["products"]


def brands_for_family(catalog: dict[str, dict], family: str) -> set[str]:
    return {p["brand"] for p in catalog.values() if p["family"] == family}
