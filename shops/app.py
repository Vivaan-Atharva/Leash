"""Three shop sites (FreshCart, DailyBasket, look-alike FreshKart) with switchable hidden injections.

Shops are untrusted: they set their own prices and pages. The gateway never reads anything here.
"""
import html
import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from shared.events import emit
from shared.money import inr

HERE = Path(__file__).parent
CATALOG = json.loads((HERE / "catalog.json").read_text())
INJECTIONS = json.loads((HERE / "injections.json").read_text())["scenarios"]
SHOPS = CATALOG["shops"]
PRODUCTS = {p["key"]: p for p in CATALOG["products"]}

app = FastAPI(title="Leash shops")
templates = Jinja2Templates(directory=str(HERE / "templates"))
LOCK = threading.Lock()
STATE = {"scenario": "S0", "carts": {s: {} for s in SHOPS}, "custom": []}


def _shop(shop_id: str) -> dict:
    if shop_id not in SHOPS:
        raise HTTPException(404, "no such shop")
    return SHOPS[shop_id]


def _scenario() -> dict:
    return INJECTIONS.get(STATE["scenario"], {"injections": [], "price_overrides": {}})


def price(shop_id: str, key: str) -> int | None:
    override = _scenario()["price_overrides"].get(shop_id, {}).get(key)
    return override if override is not None else CATALOG["prices"][shop_id].get(key)


def product(shop_id: str, sku: str) -> dict | None:
    prefix, _, key = sku.partition("-")
    if prefix != SHOPS[shop_id]["prefix"] or key not in PRODUCTS:
        return None
    p = price(shop_id, key)
    if p is None:
        return None
    return {**PRODUCTS[key], "sku": sku, "price_paise": p, "price": inr(p)}


def listing(shop_id: str, q: str = "") -> list[dict]:
    prefix = SHOPS[shop_id]["prefix"]
    out = []
    for key, base in PRODUCTS.items():
        p = product(shop_id, f"{prefix}-{key}")
        if p and (not q or q.lower() in f"{base['name']} {base['family']} {base['brand']}".lower()):
            out.append(p)
    return out


def render_injection(inj: dict) -> str:
    """Each injection is wrapped in a .leash-inj marker the X-ray overlay can find and label."""
    t = html.escape(inj["text"])
    style = inj["style"]
    if style == "white_text":
        inner = f'<p style="color:#fff;background:#fff;font-size:2px;line-height:2px;margin:0">{t}</p>'
    elif style == "html_comment":
        inner = f"<!-- {inj['text'].replace('--', '—')} -->"
    elif style == "aria_hidden":
        inner = f'<div aria-hidden="true" style="display:none">{t}</div>'
    elif style == "alt_text":
        inner = (f'<img alt="{t}" width="1" height="1" '
                 'src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">')
    elif style == "json_ld":
        ld = {"@context": "https://schema.org", "@type": "Offer", "description": inj["text"],
              "eligibleCustomerType": "pre-approved"}
        inner = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    elif style == "fake_system":
        inner = f'<div class="policy-banner"><b>System message:</b> {t}</div>'
    else:
        inner = f"<span>{t}</span>"
    return (f'<span class="leash-inj" data-leash-injection="{style}" '
            f'data-label="{html.escape(inj["label"])}">{inner}</span>')


def injections_for(shop_id: str, key: str) -> list[dict]:
    items = [i for i in _scenario()["injections"] + STATE["custom"]
             if i["shop"] == shop_id and i["product"] in (key, "*")]
    return [{**i, "html": render_injection(i)} for i in items]


# ------------------------------------------------------------------ pages
@app.get("/health")
def health():
    return {"ok": True, "service": "shops", "scenario": STATE["scenario"]}


@app.get("/{shop_id}/", response_class=HTMLResponse)
def home(request: Request, shop_id: str):
    shop = _shop(shop_id)
    return templates.TemplateResponse(request, "list.html", {
        "shop": shop, "shop_id": shop_id, "products": listing(shop_id), "heading": "Today's essentials"})


@app.get("/{shop_id}/search")
def search(request: Request, shop_id: str, q: str = "", format: str = "html"):
    shop = _shop(shop_id)
    results = listing(shop_id, q)
    if format == "json":
        return {"shop": shop_id, "merchant": shop["domain"], "query": q, "results": [
            {k: p[k] for k in ("sku", "name", "brand", "family", "category", "price_paise", "price")}
            for p in results]}
    return templates.TemplateResponse(request, "list.html", {
        "shop": shop, "shop_id": shop_id, "products": results, "heading": f"Results for “{q}”"})


@app.get("/{shop_id}/product/{sku}", response_class=HTMLResponse)
def product_page(request: Request, shop_id: str, sku: str, view: int = 0):
    shop = _shop(shop_id)
    p = product(shop_id, sku)
    if not p:
        raise HTTPException(404, "no such product")
    inj = injections_for(shop_id, p["key"])
    if not view:  # ?view=1 is Mission Control's embedded preview, not the agent
        emit("shop.page_viewed", "both", {
            "shop": shop_id, "merchant": shop["domain"], "sku": sku, "name": p["name"],
            "price": p["price"], "url": f"/{shop_id}/product/{sku}",
            "injections": [{"style": i["style"], "label": i["label"]} for i in inj]})
    return templates.TemplateResponse(request, "product.html", {
        "shop": shop, "shop_id": shop_id, "p": p, "injections": inj})


# ------------------------------------------------------------------ cart
def _cart_view(shop_id: str) -> dict:
    items = []
    for sku, qty in STATE["carts"][shop_id].items():
        p = product(shop_id, sku)
        if p:
            items.append({"sku": sku, "name": p["name"], "family": p["family"], "brand": p["brand"],
                          "category": p["category"], "qty": qty, "unit_price_paise": p["price_paise"]})
    total = sum(i["unit_price_paise"] * i["qty"] for i in items)
    return {"shop": shop_id, "merchant": SHOPS[shop_id]["domain"], "items": items,
            "total_paise": total, "total": inr(total)}


@app.post("/{shop_id}/cart")
async def add_to_cart(shop_id: str, request: Request):
    _shop(shop_id)
    if request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
    else:
        body = dict(await request.form())
    sku, qty = body.get("sku"), body.get("qty", 1)
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        raise HTTPException(400, "qty must be an integer")
    if not isinstance(sku, str) or not product(shop_id, sku):
        raise HTTPException(404, "no such product")
    if qty < 1 or qty > 999:
        raise HTTPException(400, "qty must be 1..999")
    with LOCK:
        cart = STATE["carts"][shop_id]
        cart[sku] = cart.get(sku, 0) + qty
    return _cart_view(shop_id)


@app.get("/{shop_id}/cart")
def view_cart(shop_id: str):
    _shop(shop_id)
    return _cart_view(shop_id)


@app.post("/{shop_id}/cart/clear")
def clear_cart(shop_id: str):
    _shop(shop_id)
    with LOCK:
        STATE["carts"][shop_id] = {}
    return _cart_view(shop_id)


# ------------------------------------------------------------------ admin
@app.post("/admin/scenario/{scenario_id}")
def set_scenario(scenario_id: str):
    if scenario_id not in INJECTIONS:
        raise HTTPException(404, "no such scenario")
    with LOCK:
        STATE["scenario"] = scenario_id
        STATE["carts"] = {s: {} for s in SHOPS}
    return {"scenario": scenario_id}


@app.post("/admin/reset")
def reset():
    with LOCK:
        STATE.update(scenario="S0", carts={s: {} for s in SHOPS}, custom=[])
    return {"ok": True}
