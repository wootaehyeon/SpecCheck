from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime
from app.schemas.price import (
    PriceCheckRequest,
    PriceEvaluationResult,
    MarketPricesRequest,
    MarketPricesResponse,
    PartRequest,
    PartPriceInfo,
    CrawlRequest,
    CrawlResponse,
    UsedPriceRequest,
    UsedPartPrice,
    UsedPricesResponse,
    OptimizeRequest,
)
from app.services.price_evaluation import evaluate_price
from app.services.crawl_service import crawl_related_parts, get_sample_market_reactions, crawl_dcinside_search
from app.services.naver_api import search_market_prices
from app.services.sentiment_analyzer import SentimentAnalyzer
from app.services.integrated_crawl import integrate_market_data
from app.services.ebay_api import search_used_price, get_usd_krw_rate
from app.services.used_price_optimizer import optimize_estimate

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
    """
    입력된 부품들에 대한 커뮤니티 및 중고거래 시장의 시장 반응을 수집합니다.
    DC인사이드, 네이버 카페, 당근마켓 등 다양한 소스에서 정보를 수집하고 감정분석을 수행합니다.
    """
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

@router.post("/market-intelligence")
def market_intelligence(request: CrawlRequest):
    """
    부품별 통합 시장 정보: 가격, 평가, 리뷰 채널, 위키 정보를 한 번에 제공합니다.
    - 네이버 쇼핑 가격 정보
    - YouTube 리뷰 채널
    - 나무위키 부품 정보
    - 커뮤니티 감정 평가
    """
    integrated_data = []

    for part in request.parts:
        part_name = part.name
        if not part_name:
            continue

        # 시장 반응 수집 (실제 크롤링 → 실패 시 샘플)
        try:
            market_reactions = crawl_dcinside_search(part_name, max_pages=1)
        except Exception:
            market_reactions = []
        if not market_reactions:
            market_reactions = get_sample_market_reactions(part_name)

        # 감정 분석
        analyzed_reactions = sentiment_analyzer.analyze_crawl_results(market_reactions)

        # 통합 정보
        integrated = integrate_market_data(part_name, analyzed_reactions)
        integrated_data.append(integrated)

    return {
        "status": "success",
        "data": integrated_data,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/used-prices", response_model=UsedPricesResponse)
def used_prices(request: UsedPriceRequest):
    """
    여러 부품의 해외(eBay) 중고 시세를 조회합니다.
    EBAY_OAUTH_TOKEN이 있으면 Browse API, 없으면 eBay 검색 페이지 스크래핑으로 폴백합니다.
    """
    rate = get_usd_krw_rate()
    items: List[UsedPartPrice] = []

    for part in request.parts:
        used = search_used_price(part.name)
        if not used.get("found"):
            items.append(UsedPartPrice(
                key=part.key,
                category=part.category,
                name=part.name,
                userPrice=part.userPrice,
                found=False,
                source=used.get("source"),
                error=used.get("error", "no used listings"),
            ))
            continue

        items.append(UsedPartPrice(
            key=part.key,
            category=part.category,
            name=part.name,
            userPrice=part.userPrice,
            found=True,
            source=used.get("source"),
            lowestPriceUSD=used.get("lowest_price_usd"),
            averagePriceUSD=used.get("average_price_usd"),
            lowestPriceKRW=used.get("lowest_price_krw"),
            averagePriceKRW=used.get("average_price_krw"),
            usdKrwRate=used.get("usd_krw_rate"),
            listingCount=used.get("listing_count"),
            sampleLink=used.get("sample_link"),
        ))

    return UsedPricesResponse(usdKrwRate=round(rate, 2), prices=items)


@router.post("/optimize-estimate")
def optimize_estimate_route(request: OptimizeRequest):
    """
    해외(eBay) 중고 시세를 기반으로 견적을 최적화합니다.
    - mode="save"    : 같은 부품을 중고가로 대체했을 때의 절감액
    - mode="upgrade" : 동일 예산 내에서 더 높은 성능(벤치마크)의 부품으로 교체
    - mode="both"    : 두 결과를 모두 반환 (기본값)
    """
    parts = [p.model_dump() for p in request.parts]
    result = optimize_estimate(parts, mode=request.mode, purpose=request.purpose)
    return {
        "status": "success",
        "data": result,
        "timestamp": datetime.now().isoformat(),
    }
