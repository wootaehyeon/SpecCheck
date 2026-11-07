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


class DefenderState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    antivirus_enabled: bool | None = None
    realtime_enabled: bool | None = None


class ProtectionState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    defender: DefenderState = Field(default_factory=DefenderState)
    tpm_enabled: bool | None = None
    secure_boot: bool | None = None


class EventBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: AwareDatetime
    process_key: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    kind: Literal["sysmon", "whea", "disk", "other"] = "sysmon"
    event_id: int
    count: int = Field(ge=1)


class SysmonAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "skipped", "error"]
    reason: str | None = None
    reason_code: str | None = None
    setup_status: str | None = None
    window_start: AwareDatetime | None = None
    window_end: AwareDatetime | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    truncated: bool = False
    rejected_events: int = Field(default=0, ge=0)
    buckets: list[EventBucket] = Field(default_factory=list, max_length=2000)


class AggregateSecurityData(BaseModel):
    """Basic Scan aggregates remain separate from consented process history."""
    model_config = ConfigDict(extra="forbid")
    sysmon: SysmonAggregate
    security_state: ProtectionState = Field(default_factory=ProtectionState)
