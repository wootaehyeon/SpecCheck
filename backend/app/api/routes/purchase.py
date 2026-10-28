"""실측 진단에서 연결되는 상품 검색. 모니터링 조회키를 요구하거나 전달하지 않는다."""

from fastapi import APIRouter, Query

from app.services.purchase_catalog import search_products

router = APIRouter()


@router.get('/products')
def products(query: str = Query(min_length=1, max_length=120)) -> dict:
    return search_products(query.strip())
