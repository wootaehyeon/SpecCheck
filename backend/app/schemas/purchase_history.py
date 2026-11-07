"""사용자가 직접 기록한 구매 내역. 결제 검증 데이터와 구분한다."""
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

Category = Literal["cpu", "gpu", "memory", "storage", "motherboard", "psu", "case", "cooler", "other"]


class PurchaseRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    request_id: UUID
    product_name: str = Field(min_length=1, max_length=120)
    category: Category
    unit_price: int = Field(strict=True, gt=0, le=1_000_000_000)
    quantity: int = Field(default=1, strict=True, ge=1, le=100)
    purchased_on: date
    merchant: str = Field(default="", max_length=80)
    shared: StrictBool = False

    @field_validator("purchased_on")
    @classmethod
    def no_future_purchase(cls, value: date) -> date:
        if value > datetime.now(timezone(timedelta(hours=9))).date():
            raise ValueError("구매일은 오늘(한국 시간)보다 늦을 수 없습니다.")
        return value


class PurchaseVisibility(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shared: StrictBool
