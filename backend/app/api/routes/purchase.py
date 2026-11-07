"""상품 검색·견적과 동의 기반 구매이력."""

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.purchase_catalog import search_products
from app.services.component_catalog import load_catalog
from app.services.purchase_market import offers_state
from app.services import purchase_history as history
from app.schemas.purchase_history import Category, PurchaseRecord, PurchaseVisibility

router = APIRouter(prefix="/purchase")
bearer = HTTPBearer(auto_error=False)


def purchaser(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    if not credentials or not re.fullmatch(r"sc_purchase_[a-f0-9]{64}", credentials.credentials):
        raise HTTPException(401, "이 브라우저의 구매이력 저장키가 필요합니다.", headers={"WWW-Authenticate": "Bearer"})
    return credentials.credentials


@router.get("/history")
def public_history(query: str = Query(default="", max_length=120), category: Category | None = None,
                   buyer: str | None = Query(default=None, max_length=32),
                   page: int = Query(default=1, ge=1, le=10000), page_size: int = Query(default=20, ge=1, le=100)):
    return history.listing(query=query.strip(), category=category, buyer=buyer, page=page, page_size=page_size)


@router.get("/history/me")
def my_history(query: str = Query(default="", max_length=120), category: Category | None = None,
               page: int = Query(default=1, ge=1, le=10000), page_size: int = Query(default=20, ge=1, le=100),
               token: str = Depends(purchaser)):
    return history.listing(token=token, query=query.strip(), category=category, page=page, page_size=page_size)


@router.post("/history", status_code=201)
def save_history(record: PurchaseRecord, token: str = Depends(purchaser)):
    try:
        return history.save(token, record)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.patch("/history/{record_id}")
def share_history(record_id: UUID, payload: PurchaseVisibility, token: str = Depends(purchaser)):
    record = history.set_visibility(token, str(record_id), payload.shared)
    if not record:
        raise HTTPException(404, "구매이력을 찾을 수 없습니다.")
    return record


@router.delete("/history/{record_id}", status_code=204)
def delete_history(record_id: UUID, token: str = Depends(purchaser)):
    if not history.remove(token, str(record_id)):
        raise HTTPException(404, "구매이력을 찾을 수 없습니다.")
    return Response(status_code=204)


@router.get("/quotes")
def get_quotes(product_id: list[str] = Query(default=[], max_length=32)):
    products, _ = load_catalog()
    identifiers = set(product_id)
    if identifiers - {p["id"] for p in products}:
        raise HTTPException(status_code=422, detail="카탈로그에 없는 부품입니다.")
    return offers_state([p for p in products if p["id"] in identifiers])[0]


@router.get('/products')
def products(query: str = Query(min_length=1, max_length=120)) -> dict:
    return search_products(query.strip())
