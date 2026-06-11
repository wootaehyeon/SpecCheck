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
    # /crawl, /market-intelligence 요청은 가격 없이 부품명만 보내므로 기본값 허용
    userPrice: int = 0

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

class CrawlRequest(BaseModel):
    parts: List[PartRequest]

class CrawlItem(BaseModel):
    source: str
    keyword: str
    title: str
    date: str
    url: str
    post_id: str
    collected_at: str
    content: Optional[str] = None
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None

class SentimentSummary(BaseModel):
    total: int
    positive: int
    negative: int
    neutral: int
    average_score: float
    positive_ratio: float
    negative_ratio: float

class CrawlResponse(BaseModel):
    keywords: List[str]
    results: List[CrawlItem]
    sentiment_summary: Optional[SentimentSummary] = None


# ---------------------------------------------------------------------------
# 해외(eBay) 중고가 / 견적 최적화
# ---------------------------------------------------------------------------
class UsedPriceRequest(BaseModel):
    parts: List[PartRequest]


class UsedPartPrice(BaseModel):
    key: str
    category: str
    name: str
    userPrice: int = 0
    found: bool = False
    source: Optional[str] = None
    lowestPriceUSD: Optional[float] = None
    averagePriceUSD: Optional[float] = None
    lowestPriceKRW: Optional[int] = None
    averagePriceKRW: Optional[int] = None
    usdKrwRate: Optional[float] = None
    listingCount: Optional[int] = None
    sampleLink: Optional[str] = None
    error: Optional[str] = None


class UsedPricesResponse(BaseModel):
    usdKrwRate: float
    prices: List[UsedPartPrice]


class OptimizeRequest(BaseModel):
    parts: List[PartRequest]
    # "save" | "upgrade" | "both"
    mode: str = "both"
    purpose: str = "게임"


# 최적화 응답은 동적 구조가 커서 dict로 그대로 반환합니다.
