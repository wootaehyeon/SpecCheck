"""Minimal Sysmon contract accepted by the snapshot upload API."""
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class ProcessEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: Literal[1, 5, 25, 255]
    record_id: int = Field(ge=1)
    occurred_at: AwareDatetime
    process_guid: str | None = Field(default=None, max_length=80)
    process_id: int | None = Field(default=None, ge=0)
    image: str | None = Field(default=None, max_length=260)
    parent_process_guid: str | None = Field(default=None, max_length=80)
    parent_image: str | None = Field(default=None, max_length=260)

    @field_validator("image", "parent_image")
    @classmethod
    def filename_only(cls, value):
        return PureWindowsPath(value).name if value else None


class CollectionConsent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["sysmon-minimal-v1"]
    granted_at: AwareDatetime


class SecurityData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent: CollectionConsent
    window_start: AwareDatetime
    window_end: AwareDatetime
    events: list[ProcessEvent] = Field(max_length=2000)
    truncated: bool
    log_gap: bool
    log_reset: bool
    log_oldest_at: AwareDatetime
