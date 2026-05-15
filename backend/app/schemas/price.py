from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PriceCheckRequest(BaseModel):
    component_name: str
    user_price: int

class MarketPriceInfo(BaseModel):
    lowest_price: int
    highest_price: int
    average_price: int
    collected_at: datetime
    purchase_link: Optional[str] = None

class PriceEvaluationResult(BaseModel):
    component_name: str
    user_price: int
    market_info: MarketPriceInfo
    is_overpay: bool
    evaluation_message: str
    recommend_purchase_link: Optional[str] = None
