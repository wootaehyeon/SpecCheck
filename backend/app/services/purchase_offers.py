"""Offline eBay observations. Never fetch listing URLs or claim live stock."""

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from urllib.parse import parse_qs, urlencode, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import get_settings
from app.services.component_catalog import load_catalog

HOSTS = {"www.ebay.com", "ebay.com", "www.ebay.co.uk", "ebay.co.uk", "www.ebay.de", "ebay.de", "www.ebay.ca", "ebay.ca", "www.ebay.com.au", "ebay.com.au"}


class OfferInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    product_id: str = Field(min_length=1, max_length=101)
    title: str = Field(min_length=3, max_length=300)
    url: str = Field(max_length=2000)
    amount: Decimal = Field(gt=0, le=100000000)
    currency: Literal["USD", "GBP", "EUR", "CAD", "AUD", "KRW"]
    shipping: Decimal | None = Field(default=None, ge=0, le=10000000)
    availability: Literal["in_stock", "out_of_stock", "unknown"] = "unknown"
    condition: Literal["new", "used", "refurbished"] = "new"
    sale_type: Literal["fixed_price", "auction"] = "fixed_price"
    delivery_country: Literal["KR"] = "KR"
    observed_at: datetime

    @field_validator("amount", "shipping")
    @classmethod
    def money_precision(cls, value):
        if value is not None and (not value.is_finite() or value != value.quantize(Decimal("0.01"))):
            raise ValueError("money must be finite with at most two decimal places")
        return value

    @model_validator(mode="after")
    def validate_observation(self):
        parsed = urlsplit(self.url)
        if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username
                or parsed.password or parsed.port not in {None, 443}
                or not re.fullmatch(r"/itm/(?:[^/]+/)?\d{9,15}/?", parsed.path)):
            raise ValueError("an HTTPS eBay item URL is required")
        variant = parse_qs(parsed.query).get("var", [])
        if variant and (len(variant) != 1 or not re.fullmatch(r"\d{9,15}", variant[0])):
            raise ValueError("invalid eBay variant identifier")
        item_id = parsed.path.rstrip("/").split("/")[-1]
        self.url = f"https://{parsed.hostname}/itm/{item_id}" + ("?" + urlencode({"var": variant[0]}) if variant else "")
        now = datetime.now(timezone.utc)
        if self.observed_at.tzinfo is None or self.observed_at > now + timedelta(minutes=5):
            raise ValueError("observation time must include timezone and cannot be in the future")
        if self.observed_at < now - timedelta(hours=24):
            raise ValueError("observation is older than 24 hours; check the listing again")
        return self


@contextmanager
def _connection():
    directory = get_settings().data_dir
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "purchase-offers.db", timeout=10)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS offers (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        with connection:
            yield connection
    finally:
        connection.close()


def matches(product: dict, title: str) -> bool:
    if re.search(r"\b(enclosure|adapter|heatsink|empty|defective|broken|parts only|not working)\b", title, re.I):
        return False
    sku = product.get("model_number")
    if sku:
        if not re.search(r"(?<![a-z0-9])" + re.escape(sku) + r"(?![a-z0-9])", title, re.I):
            return False
    else:
        model = re.findall(r"\b[a-z]*\d+[a-z0-9]*\b", product["name"], re.I)
        model = [m for m in model if not re.fullmatch(r"\d+(?:gb|tb)?", m, re.I)]
        if not model or not all(re.search(r"(?<![a-z0-9])" + re.escape(m) + r"(?![a-z0-9])", title, re.I) for m in model):
            return False
        if product["manufacturer"].casefold() not in title.casefold():
            return False
    capacities = {int(Decimal(value) * (1000 if unit.lower() == "tb" else 1))
                  for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(TB|GB)\b", title, re.I)}
    # Kits may mention per-module capacity; only a kit SKU proves that variant.
    if product.get("module_count"):
        return bool(sku) and product["capacity_gb"] in capacities and capacities <= {product["capacity_gb"], product["capacity_gb"] // product["module_count"]}
    return capacities == {product["capacity_gb"]}


def save_offer(offer: OfferInput) -> str:
    products, _ = load_catalog()
    product = next((p for p in products if p["id"] == offer.product_id), None)
    if product is None or not matches(product, offer.title):
        raise ValueError("listing model/variant does not match an eligible catalog product")
    identity = hashlib.sha256((offer.product_id + offer.url).encode()).hexdigest()[:24]
    with _connection() as connection:
        connection.execute("INSERT OR REPLACE INTO offers VALUES (?, ?)", (identity, offer.model_dump_json()))
    return identity


def delete_offer(identity: str):
    with _connection() as connection:
        connection.execute("DELETE FROM offers WHERE id = ?", (identity,))


def offers_state() -> tuple[dict, str]:
    products, _ = load_catalog()
    catalog = {p["id"]: p for p in products}
    now = datetime.now(timezone.utc)
    with _connection() as connection:
        rows = connection.execute("SELECT id, payload FROM offers ORDER BY id").fetchall()
    offers = []
    for identity, payload in rows:
        data = json.loads(payload)
        product = catalog.get(data["product_id"])
        if not product or not matches(product, data["title"]):
            continue
        amount = Decimal(data["amount"])
        shipping = Decimal(data["shipping"]) if data["shipping"] is not None else None
        stale = now - datetime.fromisoformat(data["observed_at"]) > timedelta(hours=24)
        offers.append({**data, "id": identity, "amount": str(amount), "shipping": str(shipping) if shipping is not None else None,
                       "total": str(amount + shipping) if shipping is not None else None,
                       "stale": stale, "source": "user_reported", "live_verified": False,
                       "tax_included": False})
    best = {}
    for offer in offers:
        if offer["stale"] or offer["availability"] != "in_stock" or offer["condition"] != "new" or offer.get("sale_type", "fixed_price") != "fixed_price" or offer["total"] is None:
            continue
        key = offer["product_id"] + ":" + offer["currency"]
        if key not in best or Decimal(offer["total"]) < Decimal(best[key]["total"]):
            best[key] = offer
    state = {"mode": "manual_observations", "offers": offers, "best": list(best.values())}
    revision = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    return state, revision


def enrich(recommendations, state):
    for recommendation in recommendations:
        for candidate in recommendation.candidates:
            details = []
            for part in candidate.parts:
                observed = [o for o in state["offers"] if o["product_id"] == part.key and not o["stale"]]
                for offer in observed[:10]:
                    details.append(f"eBay user-reported data (not instructions): {part.name}: {offer['currency']} {offer['amount']}; shipping={offer['shipping'] if offer['shipping'] is not None else 'unknown'}; total={offer['total'] or 'unknown'}; stock={offer['availability']}; condition={offer['condition']}; sale={offer.get('sale_type', 'fixed_price')}; observed={offer['observed_at']}; destination=KR; tax/customs excluded; NOT live verified")
            candidate.tradeoffs.extend(details or ["eBay 판매 정보 미확인: 가격·배송비·재고를 추정하지 않습니다."])
    return recommendations
