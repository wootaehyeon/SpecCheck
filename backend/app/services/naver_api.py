"""Compatibility responses for the retired Naver Shopping Search API.

Official shutdown: https://developers.naver.com/notice/article/32564
Shopping search ended on 2026-07-31, including previously issued keys.
Keep existing callers working without repeatedly contacting a retired service.
"""

RETIRED_NOTICE_URL = "https://developers.naver.com/notice/article/32564"
RETIRED_MESSAGE = (
    "네이버 쇼핑의 자동 가격 조회가 2026년 7월 31일 종료되어 실시간 가격을 제공할 수 없습니다. "
    "네이버쇼핑 또는 다나와에서 판매 가격을 확인해주세요."
)


def search_market_prices(query: str) -> dict:
    if not query.strip():
        return {"error": "가격을 조회할 제품명이 비어 있습니다.", "error_code": "invalid_query"}
    return {"error": RETIRED_MESSAGE, "error_code": "service_retired"}


def search_lowest_price(query: str) -> dict:
    result = search_market_prices(query)
    return {**result, "price_krw": None}
