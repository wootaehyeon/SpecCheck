"""Security collector (Phase 7 / M6-M7) - 구현 예정 스텁.

Advanced Scan 영역. Sysmon 설치를 전제로 한다.

수집 대상:

- Sysmon 이벤트 (Microsoft-Windows-Sysmon/Operational)
  EventID 1(Process Create), 3(Network Connect), 11(File Create),
  13(Registry Set), 22(DNS Query)
- 기본 보안 상태
  ``MSFT_MpComputerStatus`` (root/microsoft/windows/defender)
  ``Win32_Tpm`` (root/cimv2/security/microsofttpm), Secure Boot 여부

설계 노트: 보안 이벤트는 그 자체로 결론이 아니라 성능 저하의 원인 후보다.
"게임이 느려졌다"의 원인이 크립토마이너나 부팅 시 자동 실행 프로그램 과다인
경우, 정답은 구매가 아니라 Software Fix다. M7의 Event Correlation이
이 판단을 담당한다.
"""

from __future__ import annotations

from typing import Any

from .base import Collector, register


@register
class SecurityCollector(Collector):
    name = "security"
    milestone = "M6"
    description = "Sysmon 기반 프로세스/네트워크/파일 이벤트"
    implemented = False

    def collect(self) -> dict[str, Any]:
        raise NotImplementedError("M6에서 구현")
