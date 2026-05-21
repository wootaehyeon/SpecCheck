from pydantic import BaseModel
from typing import Optional, List
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

class PartRequest(BaseModel):
    key: str
    category: str
    name: str
    userPrice: int

class PartPriceInfo(BaseModel):
    key: str
    category: str
    name: str
    userPrice: int
    lowestPrice: int
    highestPrice: int
    averagePrice: int
    purchaseLink: Optional[str]
    mall: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None

class MarketPricesRequest(BaseModel):
    parts: List[PartRequest]

class MarketPricesResponse(BaseModel):
    prices: List[PartPriceInfo]
