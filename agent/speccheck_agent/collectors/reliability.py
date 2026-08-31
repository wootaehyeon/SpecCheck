"""Reliability collector (Phase 2 / M2) - 구현 예정 스텁.

하드웨어 결함의 직접 증거를 이벤트 로그에서 찾는다.

수집 대상:

- WHEA (Windows Hardware Error Architecture)
  ``Get-WinEvent -LogName System -FilterXPath`` Provider=Microsoft-Windows-WHEA-Logger
  EventID 17(Corrected), 18(Fatal), 19(Corrected) - 메모리/PCIe/CPU 오류
- 비정상 종료 / 블루스크린
  System 로그 EventID 41(Kernel-Power), 1001(BugCheck), 6008(Unexpected shutdown)
- 디스크 오류
  System 로그 EventID 7(disk), 51(paging error), 153(IO retry)

설계 노트: Root Cause Analysis에서 WHEA는 "증상"이 아니라 "결함의 직접 증거"다.
정정 가능 오류(Corrected)가 누적되는 패턴은 아직 체감 증상이 없어도
부품 교체 필요성을 예측하는 강한 신호이며, What-if Scan의 근거가 된다.
"""

from __future__ import annotations

from typing import Any

from .base import Collector, register


@register
class ReliabilityCollector(Collector):
    name = "reliability"
    milestone = "M2"
    description = "WHEA / 비정상 종료 / 디스크 오류 이벤트"
    implemented = False

    def collect(self) -> dict[str, Any]:
        raise NotImplementedError("M2에서 구현")
