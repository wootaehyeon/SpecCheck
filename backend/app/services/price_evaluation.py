from datetime import datetime
from app.schemas.price import PriceCheckRequest, MarketPriceInfo, PriceEvaluationResult
from app.services.naver_api import search_market_prices

def evaluate_price(request: PriceCheckRequest) -> PriceEvaluationResult:
    """
    사용자가 입력한 가격과 네이버 API로 가져온 최신 시세를 비교하여 결과를 반환합니다.
    """
    market_data = search_market_prices(request.component_name)
    
    # 에러 처리
    if "error" in market_data:
        # API 오류 혹은 상품 없음
        return PriceEvaluationResult(
            component_name=request.component_name,
            user_price=request.user_price,
            market_info=MarketPriceInfo(
                lowest_price=0,
                highest_price=0,
                average_price=0,
                collected_at=datetime.now(),
                purchase_link=None
            ),
            is_overpay=False,
            evaluation_message=f"시세 정보를 불러올 수 없습니다. ({market_data['error']})",
            recommend_purchase_link=None
        )
        
    avg_price = market_data["average_price"]
    lowest_price = market_data["lowest_price"]
    
    # 오버페이 기준 설정 (예: 평균가의 105% 초과시 오버페이)
    overpay_threshold = avg_price * 1.05
    is_overpay = request.user_price > overpay_threshold
    
    if is_overpay:
        diff = request.user_price - avg_price
        eval_msg = f"시세 대비 약 {diff:,}원 비싸게 구매하시려고 합니다. 최저가 상품 구매를 추천합니다."
    elif request.user_price <= lowest_price * 1.05:
        eval_msg = "최저가에 근접한 아주 좋은 가격입니다!"
    else:
        eval_msg = "평균 시세에 맞는 적절한 가격입니다."
        
    market_info = MarketPriceInfo(
        lowest_price=lowest_price,
        highest_price=market_data["highest_price"],
        average_price=avg_price,
        collected_at=datetime.now(),
        purchase_link=market_data.get("purchase_link")
    )
    
    return PriceEvaluationResult(
        component_name=request.component_name,
        user_price=request.user_price,
        market_info=market_info,
        is_overpay=is_overpay,
        evaluation_message=eval_msg,
        recommend_purchase_link=market_info.purchase_link if is_overpay else None
    )

if __name__ == "__main__":
    # Test script
    req = PriceCheckRequest(component_name="AMD Ryzen 5 5600X", user_price=200000)
    result = evaluate_price(req)
    print(result.model_dump_json(indent=2))
