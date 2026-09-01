"""표준 스냅샷 생성.

형식 정의는 ``shared/contracts/telemetry_snapshot.schema.json`` 에 있다.
스키마를 바꾸면 SCHEMA_VERSION과 Backend의 SUPPORTED_SCHEMA_MAJOR도 함께 올린다.
"""

from __future__ import annotations

import hashlib
import platform
import socket
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from . import __version__
from .collectors.base import CollectorResult

SCHEMA_VERSION = "1.1.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_device_id() -> str:
    """호스트명 기반 익명 식별자.

    telemetry를 외부로 내보내지 않는다는 원칙에 따라 호스트명 원문 대신
    되돌릴 수 없는 해시만 사용한다. 시계열 비교(예측 -> 검증)의 키 역할.
    """
    raw = "%s|%s" % (socket.gethostname(), platform.machine())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def build_snapshot(
    results: Iterable[CollectorResult],
    scan_mode: str = "actual",
    device_id: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """collector 결과들을 계약 형식의 dict 하나로 합친다."""
    sections: dict[str, Any] = {}
    for result in results:
        sections[result.name] = result.to_section()

    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": str(uuid.uuid4()),
        "collected_at": _now_iso(),
        "scan_mode": scan_mode,
        "device_id": device_id or default_device_id(),
        "agent": {
            "version": __version__,
            "os": platform.system(),
            "os_version": platform.version(),
            "python": sys.version.split()[0],
        },
        "sections": sections,
        "notes": notes,
    }


def summarize(snapshot: dict[str, Any]) -> str:
    """CLI 출력용 한 줄 요약."""
    sections = snapshot.get("sections", {})
    counts: dict[str, int] = {}
    for section in sections.values():
        status = section.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    detail = ", ".join("%s=%d" % item for item in sorted(counts.items()))
    return "%s | %s | %s" % (snapshot.get("snapshot_id", "?")[:8], snapshot.get("collected_at"), detail)
