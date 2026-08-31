"""AI Diagnosis 계층.

    Telemetry Snapshot -> Rule Detection(M4) -> Findings
                       -> Action Decision -> LLM 설명(M5)

규칙 엔진과 LLM의 역할을 분리한다. 판정은 규칙이 하고, LLM은 이미 내려진
판정을 사람이 읽을 수 있게 옮길 뿐이다. 모델이 진단을 지어내지 못하게
막는 구조적 장치다.
"""

from .engine import Rule, diagnose, register, registry
from . import rules  # noqa: F401  import 시점에 규칙 등록

__all__ = ["Rule", "diagnose", "register", "registry"]
