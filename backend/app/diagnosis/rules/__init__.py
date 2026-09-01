"""진단 규칙 모음.

여기서 import 하는 모듈의 규칙만 엔진 레지스트리에 등록된다.

| 축 | 모듈 | 근거 telemetry | 상태 |
| --- | --- | --- | --- |
| Hardware | ``hardware_rules`` | M1 인벤토리 | M4 |
| Software | ``software_rules`` | M1 인벤토리 | M4 |
| Storage | ``storage_rules`` | M2 ``storage_health`` | M4 |
| Reliability | ``reliability_rules`` | M2 ``reliability`` | M4 |
| Performance | ``performance_rules`` | M2 ``performance`` | M4 |
| Security | ``security_rules`` | M6 ``security`` | M7에서 추가 예정 |

M2 기반 모듈의 규칙들은 해당 섹션이 없으면 실행되지 않는다(``Rule.requires``).
Agent 미설치·권한 부족·구버전 Agent에서 "이상 없음"이 아니라 "확인하지 못함"이
되도록 하기 위한 장치다.
"""

from . import hardware_rules  # noqa: F401
from . import software_rules  # noqa: F401
from . import storage_rules  # noqa: F401
from . import reliability_rules  # noqa: F401
from . import performance_rules  # noqa: F401
