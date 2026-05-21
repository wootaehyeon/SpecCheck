from fastapi import APIRouter, HTTPException
from typing import List
from app.schemas.price import (
    PriceCheckRequest,
    PriceEvaluationResult,
    MarketPricesRequest,
    MarketPricesResponse,
    PartPriceInfo,
)
from app.services.price_evaluation import evaluate_price
from app.services.naver_api import search_market_prices
from app.schemas.evaluation import BuildRequest, EvaluationResult
from app.logic.risk_score import compute_risk

router = APIRouter()

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


@router.post("/evaluate-build", response_model=EvaluationResult)
def evaluate_build(request: BuildRequest):
    """CPU/GPU 성능 평가, 호환성 검사, 구매 위험도 점수 계산 후 반환합니다."""
    build = request.dict()
    risk = compute_risk(build)

    eval_data = risk.get("evaluation", {})
    comp = risk.get("compatibility", {})
    breakdown = risk.get("breakdown", {})

    # map to response model
    return EvaluationResult(
        cpu_matched=eval_data.get("cpu_matched"),
        cpu_score=eval_data.get("cpu_score", 0),
        gpu_matched=eval_data.get("gpu_matched"),
        gpu_score=eval_data.get("gpu_score", 0),
        overall_score=eval_data.get("overall_score", 0),
        tier=eval_data.get("tier", ""),
        compatibility={
            "issues": comp.get("issues", []),
            "estimated_required_watt": comp.get("estimated_required_watt", 0),
            "recommended_psu_watt": comp.get("recommended_psu_watt", 0),
        },
        risk_score=risk.get("risk_score", 0),
        risk_breakdown=breakdown,
    )
