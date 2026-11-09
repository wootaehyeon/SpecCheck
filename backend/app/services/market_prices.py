"""Use eBay quotes without treating a native currency as Korean won."""

from decimal import Decimal

from app.services.purchase_catalog import search_products


def search_market_prices(query: str) -> dict:
    result = search_products(query)
    products = result["products"]
    if not products:
        return {"error": result.get("message", "동일 모델의 eBay 판매 상품을 찾지 못했습니다."),
                "error_code": result["status"], "source": "ebay_browse"}
    groups = {}
    for product in products:
        groups.setdefault(product["currency"], []).append(product)
    native = []
    for currency, items in sorted(groups.items()):
        amounts = [Decimal(item["amount"]) for item in items]
        native.append({"currency": currency, "lowest": str(min(amounts)), "highest": str(max(amounts)),
                       "average": str((sum(amounts) / len(amounts)).quantize(Decimal("0.01"))), "listingCount": len(items)})
    group = groups.get("KRW", groups[sorted(groups)[0]])
    lowest = min(group, key=lambda item: Decimal(item["amount"]))
    metadata = {"native_prices": native, "purchase_link": lowest["url"], "product_title": lowest["title"],
                "listing_count": len(products), "mall": "eBay", "source": "ebay_browse", "cached": result.get("cached", False)}
    if "KRW" not in groups:
        return {**metadata, "error_code": "currency_mismatch",
                "error": "eBay 판매가는 원래 통화로 표시합니다. 원화 견적과 자동 비교하지 않으며 한국 배송비·관세·부가세는 별도 확인이 필요합니다."}
    amounts = [Decimal(item["amount"]) for item in groups["KRW"]]
    return {**metadata, "lowest_price": int(min(amounts)), "highest_price": int(max(amounts)),
            "average_price": int(sum(amounts) / len(amounts))}


def search_lowest_price(query: str) -> dict:
    result = search_market_prices(query)
    return {**result, "price_krw": result.get("lowest_price"), "title": result.get("product_title"), "link": result.get("purchase_link")}
