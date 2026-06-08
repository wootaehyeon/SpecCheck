from fastapi import APIRouter, HTTPException
from typing import List
from app.schemas.price import (
    PriceCheckRequest,
    PriceEvaluationResult,
    MarketPricesRequest,
    MarketPricesResponse,
    PartRequest,
    PartPriceInfo,
    CrawlRequest,
    CrawlResponse,
)
from app.services.price_evaluation import evaluate_price
from app.services.crawl_service import crawl_related_parts
from app.services.naver_api import search_market_prices
from app.services.sentiment_analyzer import SentimentAnalyzer

router = APIRouter()
sentiment_analyzer = SentimentAnalyzer()

@router.post("/price-check", response_model=PriceEvaluationResult)
def check_price(request: PriceCheckRequest):
    """
    부품의 가격을 확인하고 시세 대비 오버페이 여부를 평가합니다.
    """
    result = evaluate_price(request)

    if result.market_info.average_price == 0:
        raise HTTPException(status_code=404, detail=result.evaluation_message)

    return result

@router.post("/market-prices", response_model=MarketPricesResponse)
def market_prices(request: MarketPricesRequest):
    """
    여러 부품의 네이버 쇼핑 시세를 조회하여 프론트엔드에서 가공할 수 있는 데이터를 제공합니다.
    """
    response_items: List[PartPriceInfo] = []

    for part in request.parts:
        market_data = search_market_prices(part.name)
        if "error" in market_data:
            response_items.append(
                PartPriceInfo(
                    key=part.key,
                    category=part.category,
                    name=part.name,
                    userPrice=part.userPrice,
                    lowestPrice=0,
                    highestPrice=0,
                    averagePrice=0,
                    purchaseLink=None,
                    mall=None,
                    source="error",
                    error=market_data.get("error")
                )
            )
            continue

        response_items.append(
            PartPriceInfo(
                key=part.key,
                category=part.category,
                name=part.name,
                userPrice=part.userPrice,
                lowestPrice=market_data["lowest_price"],
                highestPrice=market_data["highest_price"],
                averagePrice=market_data["average_price"],
                purchaseLink=market_data.get("purchase_link"),
                mall="Naver 쇼핑",
                source="naver",
                error=None
            )
        )

    return MarketPricesResponse(prices=response_items)

@router.post("/crawl", response_model=CrawlResponse)
def crawl(request: CrawlRequest):
    search_results = crawl_related_parts(request.parts)

    # Apply sentiment analysis
    analyzed_results = sentiment_analyzer.analyze_crawl_results(search_results)

    # Get sentiment summary
    sentiment_summary = sentiment_analyzer.get_sentiment_summary(analyzed_results)

    return CrawlResponse(
        keywords=[part.name for part in request.parts if part.name],
        results=analyzed_results,
        sentiment_summary=sentiment_summary,
    )
