"""Read-only shopping quotes for validated catalog products."""

from fastapi import APIRouter, HTTPException, Query

from app.services.component_catalog import load_catalog
from app.services.purchase_market import offers_state

router = APIRouter(prefix="/purchase")


@router.get("/quotes")
def get_quotes(product_id: list[str] = Query(default=[], max_length=32)):
    products, _ = load_catalog()
    identifiers = set(product_id)
    if identifiers - {p["id"] for p in products}:
        raise HTTPException(status_code=422, detail="카탈로그에 없는 부품입니다.")
    return offers_state([p for p in products if p["id"] in identifiers])[0]
