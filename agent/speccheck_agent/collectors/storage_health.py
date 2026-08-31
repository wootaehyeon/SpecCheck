"""Storage Health collector (Phase 2 / M2) - 구현 예정 스텁.

하드웨어 인벤토리(``hardware`` collector)가 "무엇이 달렸는가"를 본다면
이 collector는 "얼마나 닳았는가"를 본다.

수집 대상:

- SMART 속성
  ``MSStorageDriver_FailurePredictStatus`` / ``...PredictData`` (root/wmi)
  재할당 섹터(05), 대기 섹터(C5), 통전 시간(09), 쓰기 총량(F1/F2)
- NVMe 수명
  ``Get-PhysicalDisk | Get-StorageReliabilityCounter`` (Wear, Temperature)
- 볼륨 여유 공간
  ``Win32_LogicalDisk`` (DriveType=3, FreeSpace, Size)

설계 노트: 시스템 드라이브 여유 공간 부족은 체감 성능 저하의 가장 흔한
원인이면서 "구매하지 않아도 되는" 대표 사례다. No-Purchase Scenario의
핵심 근거가 되므로 우선 구현한다.
"""

from __future__ import annotations

from typing import Any

from .base import Collector, register


@register
class StorageHealthCollector(Collector):
    name = "storage_health"
    milestone = "M2"
    description = "SMART / 수명 / 볼륨 여유 공간"
    implemented = False

    def collect(self) -> dict[str, Any]:
        raise NotImplementedError("M2에서 구현")
