"""Collector 공통 계약과 레지스트리.

새 telemetry를 추가하는 방법:

1. 이 모듈의 ``Collector`` 를 상속한 클래스를 ``collectors/`` 안에 만든다.
2. ``@register`` 데코레이터를 붙인다.
3. ``collectors/__init__.py`` 에서 모듈을 import 한다.

collect()가 예외를 던져도 스캔 전체는 중단되지 않는다. 해당 섹션만
status="error"로 기록되고 나머지 collector는 계속 실행된다.
"""

from __future__ import annotations

import platform
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

Status = str  # "ok" | "partial" | "skipped" | "planned" | "error"


@dataclass
class CollectorResult:
    name: str
    status: Status
    milestone: str | None = None
    duration_ms: float | None = None
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_section(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "milestone": self.milestone,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "data": self.data,
        }


class Collector(ABC):
    """telemetry 수집 단위."""

    #: 스냅샷 sections의 키
    name: str = "unnamed"
    #: 로드맵 상 담당 마일스톤 (M1 ~ M10)
    milestone: str = "M1"
    #: 사람이 읽는 설명
    description: str = ""
    #: Windows 전용 여부
    requires_windows: bool = True
    #: False면 실행하지 않고 status="planned"로 기록 (미구현 스텁)
    implemented: bool = True

    def available(self) -> tuple[bool, str | None]:
        """실행 가능 여부와 불가 사유."""
        if self.requires_windows and platform.system() != "Windows":
            return False, "Windows 전용 collector (현재: %s)" % platform.system()
        return True, None

    @abstractmethod
    def collect(self) -> dict[str, Any]:
        """실제 수집. 반환값이 그대로 section.data 가 된다."""

    def run(self) -> CollectorResult:
        if not self.implemented:
            return CollectorResult(
                name=self.name,
                status="planned",
                milestone=self.milestone,
                error="%s에서 구현 예정" % self.milestone,
            )

        ok, reason = self.available()
        if not ok:
            return CollectorResult(
                name=self.name, status="skipped", milestone=self.milestone, error=reason
            )

        started = time.perf_counter()
        try:
            data = self.collect()
        except Exception as exc:  # collector 하나의 실패가 스캔 전체를 막지 않는다
            return CollectorResult(
                name=self.name,
                status="error",
                milestone=self.milestone,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                error="%s: %s" % (type(exc).__name__, exc),
            )

        elapsed = round((time.perf_counter() - started) * 1000, 1)
        status = "partial" if data.get("_partial") else "ok"
        data.pop("_partial", None)
        return CollectorResult(
            name=self.name,
            status=status,
            milestone=self.milestone,
            duration_ms=elapsed,
            data=data,
        )


_REGISTRY: dict[str, type[Collector]] = {}


def register(cls: type[Collector]) -> type[Collector]:
    """Collector 클래스를 전역 레지스트리에 등록하는 데코레이터."""
    if cls.name in _REGISTRY:
        raise ValueError("collector 이름 중복: %s" % cls.name)
    _REGISTRY[cls.name] = cls
    return cls


def registry() -> dict[str, type[Collector]]:
    return dict(_REGISTRY)


def iter_collectors(names: list[str] | None = None) -> Iterator[Collector]:
    """이름 목록에 해당하는 collector 인스턴스를 순서대로 생성한다."""
    available = registry()
    selected = names or list(available)
    for name in selected:
        cls = available.get(name)
        if cls is None:
            raise KeyError("알 수 없는 collector: %s (사용 가능: %s)" % (name, ", ".join(available)))
        yield cls()
