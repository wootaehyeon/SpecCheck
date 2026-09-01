"""Reliability collector (Phase 2 / M2).

하드웨어 결함의 직접 증거를 이벤트 로그에서 찾는다.

데이터 소스 (모두 System 로그, 관리자 권한 없이 읽을 수 있다)

- WHEA (Windows Hardware Error Architecture)
  Provider ``Microsoft-Windows-WHEA-Logger``, EventID 17/19/47(Corrected), 18(Fatal)
- 비정상 종료 / 블루스크린
  ``Microsoft-Windows-Kernel-Power`` 41, ``...WER-SystemErrorReporting`` 1001, ``EventLog`` 6008
- 디스크 / 파일시스템 오류
  ``disk`` 7(불량 블록) / 11(컨트롤러 오류) / 51(페이징 오류) / 153(IO 재시도), ``Ntfs`` 55

설계 노트: Root Cause Analysis에서 WHEA는 "증상"이 아니라 "결함의 직접 증거"다.
정정 가능 오류(Corrected)가 누적되는 패턴은 아직 체감 증상이 없어도
부품 교체 필요성을 예측하는 강한 신호이며, What-if Scan의 근거가 된다.

이벤트 **원문은 담지 않는다.** EventID별 건수와 최초/최종 발생 시각, 관측 구간만
남긴다. 원문 로그는 용량과 프라이버시 양쪽에서 비용이고, 규칙이 필요로 하는 것은
"얼마나 자주, 언제까지 났는가"뿐이다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from ..win import cim
from .base import Collector, register

#: 관측 구간 기본값. 너무 짧으면 산발적 오류를 놓치고, 너무 길면 이미 해결된
#: 과거 문제를 현재 결함으로 오판한다.
DEFAULT_WINDOW_DAYS = 30

#: (provider 소문자, EventID) -> (분류, 사람이 읽는 설명)
#: 화이트리스트 밖의 이벤트는 세지 않는다. 규칙이 근거로 쓸 수 있는 것만 남긴다.
EVENT_CATALOG: dict[tuple[str, int], tuple[str, str]] = {
    ("microsoft-windows-whea-logger", 17): ("whea_corrected", "정정된 하드웨어 오류"),
    ("microsoft-windows-whea-logger", 19): ("whea_corrected", "정정된 하드웨어 오류 (캐시/메모리)"),
    ("microsoft-windows-whea-logger", 47): ("whea_corrected", "정정된 메모리 오류"),
    ("microsoft-windows-whea-logger", 18): ("whea_fatal", "치명적 하드웨어 오류"),
    ("microsoft-windows-kernel-power", 41): ("unexpected_shutdown", "정상 종료 없이 재부팅됨"),
    ("eventlog", 6008): ("unexpected_shutdown", "예기치 않은 시스템 종료"),
    ("microsoft-windows-wer-systemerrorreporting", 1001): ("bugcheck", "블루스크린 (BugCheck)"),
    ("bugcheck", 1001): ("bugcheck", "블루스크린 (BugCheck)"),
    ("disk", 7): ("disk_error", "디스크에 불량 블록"),
    ("disk", 11): ("disk_error", "디스크 컨트롤러 오류"),
    ("disk", 51): ("disk_error", "페이징 작업 중 오류"),
    ("disk", 153): ("disk_error", "디스크 IO 재시도"),
    ("volmgr", 161): ("disk_error", "덤프 파일 생성 실패"),
    ("ntfs", 55): ("filesystem_error", "파일 시스템 구조 손상"),
}

#: totals에 항상 존재하는 키. 규칙이 "값이 없다"와 "0건이다"를 구분할 필요가 없도록
#: 관측이 성공하면 모든 분류를 0으로 채워 내보낸다.
CATEGORIES = ("whea_corrected", "whea_fatal", "unexpected_shutdown", "bugcheck", "disk_error", "filesystem_error")

_PROVIDERS = sorted({provider for provider, _ in EVENT_CATALOG})
_EVENT_IDS = sorted({event_id for _, event_id in EVENT_CATALOG})

#: Get-WinEvent은 CIM이 아니므로 스크립트로 직접 돈다. 필터를 FilterHashtable로
#: 넘겨야 로그 전체를 훑지 않고 인덱스로 걸러낸다 (수만 건 로그에서 수십 배 차이).
_QUERY_SCRIPT = """
$start = (Get-Date).AddDays(-{days})
$filter = @{{
    LogName      = 'System'
    StartTime    = $start
    ProviderName = @({providers})
    Id           = @({ids})
}}
$events = @(Get-WinEvent -FilterHashtable $filter -ErrorAction SilentlyContinue)
$groups = @()
foreach ($group in ($events | Group-Object ProviderName, Id)) {{
    $sorted = $group.Group | Sort-Object TimeCreated
    $groups += [pscustomobject]@{{
        Provider = $sorted[0].ProviderName
        EventId  = $sorted[0].Id
        Count    = $group.Count
        FirstAt  = $sorted[0].TimeCreated.ToUniversalTime().ToString('o')
        LastAt   = $sorted[-1].TimeCreated.ToUniversalTime().ToString('o')
    }}
}}
$oldest = Get-WinEvent -LogName System -MaxEvents 1 -Oldest -ErrorAction SilentlyContinue
$oldestAt = $null
if ($oldest) {{ $oldestAt = $oldest.TimeCreated.ToUniversalTime().ToString('o') }}
[ordered]@{{ Groups = $groups; LogOldestAt = $oldestAt }} | ConvertTo-Json -Depth 4 -Compress
"""


def window_days() -> int:
    """관측 구간(일). ``SPECCHECK_RELIABILITY_DAYS`` 로 조정한다."""
    raw = os.environ.get("SPECCHECK_RELIABILITY_DAYS")
    try:
        days = int(raw) if raw else DEFAULT_WINDOW_DAYS
    except ValueError:
        return DEFAULT_WINDOW_DAYS
    return days if 1 <= days <= 365 else DEFAULT_WINDOW_DAYS


def build_script(days: int) -> str:
    """관측 구간을 끼워 넣은 PowerShell 스크립트."""
    return _QUERY_SCRIPT.format(
        days=days,
        providers=", ".join("'{0}'".format(name) for name in _PROVIDERS),
        ids=", ".join(str(event_id) for event_id in _EVENT_IDS),
    ).strip()


@register
class ReliabilityCollector(Collector):
    name = "reliability"
    milestone = "M2"
    description = "WHEA / 비정상 종료 / 디스크 오류 이벤트"

    def collect(self) -> dict[str, Any]:
        days = window_days()
        raw = cim.run_powershell(build_script(days), timeout=cim.BATCH_TIMEOUT).strip()

        parsed: dict[str, Any] = {}
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise cim.CimError("이벤트 로그 응답 JSON 파싱 실패: {0}".format(raw[:200])) from exc

        groups = parsed.get("Groups")
        if isinstance(groups, dict):  # 그룹이 1개면 PowerShell이 배열로 감싸지 않는다
            groups = [groups]

        return shape_reliability(
            groups or [],
            days=days,
            log_oldest_at=parsed.get("LogOldestAt"),
        )


# --- 정규화 함수 -------------------------------------------------------------


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def shape_reliability(
    groups: list[dict[str, Any]],
    days: int = DEFAULT_WINDOW_DAYS,
    log_oldest_at: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """(provider, EventID) 그룹 집계를 계약 형식으로 바꾼다."""
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    events: list[dict[str, Any]] = []
    totals = {category: 0 for category in CATEGORIES}
    unmatched = 0

    for group in groups:
        provider = str(group.get("Provider") or "").strip()
        event_id = _to_int(group.get("EventId"))
        count = _to_int(group.get("Count")) or 0
        if event_id is None or count <= 0:
            continue

        known = EVENT_CATALOG.get((provider.lower(), event_id))
        if known is None:
            # 필터를 통과했지만 카탈로그에 없는 조합. 세기만 하고 판정에는 쓰지 않는다.
            unmatched += count
            continue

        category, label = known
        totals[category] += count
        events.append(
            {
                "provider": provider,
                "event_id": event_id,
                "category": category,
                "label": label,
                "count": count,
                "first_at": group.get("FirstAt"),
                "last_at": group.get("LastAt"),
            }
        )

    events.sort(key=lambda event: event["count"], reverse=True)

    return {
        "window_days": days,
        "window_start": start.isoformat(timespec="seconds"),
        "window_end": end.isoformat(timespec="seconds"),
        # 로그가 관측 구간보다 짧게 보관돼 있으면 "0건"이 "이상 없음"을 뜻하지 않는다.
        # 규칙이 이 값을 보고 신뢰도를 낮출 수 있도록 함께 남긴다.
        "log_oldest_at": log_oldest_at,
        "log_covers_window": _covers_window(log_oldest_at, start),
        "events": events,
        "totals": totals,
        "unmatched_events": unmatched,
    }


def _covers_window(log_oldest_at: str | None, window_start: datetime) -> bool | None:
    if not log_oldest_at:
        return None
    try:
        oldest = datetime.fromisoformat(str(log_oldest_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    return oldest <= window_start
