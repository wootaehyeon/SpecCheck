from fastapi import APIRouter, HTTPException
from app.schemas.price import PriceCheckRequest, PriceEvaluationResult
from app.services.price_evaluation import evaluate_price

router = APIRouter()

@router.post("/price-check", response_model=PriceEvaluationResult)
def check_price(request: PriceCheckRequest):
    """
    부품의 가격을 확인하고 시세 대비 오버페이 여부를 평가합니다.
    """
    result = evaluate_price(request)
    
    # 만약 시세 조회를 실패한 경우 (error 메시지가 반환됨)
    if result.market_info.average_price == 0:
        raise HTTPException(status_code=404, detail=result.evaluation_message)
        
    return result
