"""Performance collector (Phase 2 / M2) - 구현 예정 스텁.

수집 대상 (구현 시 참고할 데이터 소스):

- CPU/메모리/디스크 사용률
  ``Win32_PerfFormattedData_PerfOS_Processor`` (PercentProcessorTime)
  ``Win32_PerfFormattedData_PerfOS_Memory`` (AvailableMBytes, PagesPerSec)
  ``Win32_PerfFormattedData_PerfDisk_PhysicalDisk`` (AvgDiskQueueLength)
- 온도 / 스로틀링
  ``MSAcpi_ThermalZoneTemperature`` (root/wmi) - 미지원 메인보드 다수
  ``Win32_Processor.CurrentClockSpeed`` 와 MaxClockSpeed 비율로 간접 추정
- 전원 계획
  ``Win32_PowerPlan`` (root/cimv2/power) - 절전 모드로 인한 성능 저하 판별

설계 노트: 단발성 값은 진단 근거로 약하다. 짧은 샘플링 구간(예: 5초 x 3회)의
평균/최대를 함께 담아 스파이크와 상시 부하를 구분할 수 있게 한다.
"""

from __future__ import annotations

from typing import Any

from .base import Collector, register


@register
class PerformanceCollector(Collector):
    name = "performance"
    milestone = "M2"
    description = "성능 카운터 샘플링 (CPU/메모리/디스크/온도)"
    implemented = False

    def collect(self) -> dict[str, Any]:
        raise NotImplementedError("M2에서 구현")
