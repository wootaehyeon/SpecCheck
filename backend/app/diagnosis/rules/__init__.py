"""진단 규칙 모음.

여기서 import 하는 모듈의 규칙만 엔진 레지스트리에 등록된다.

| 축 | 모듈 | 상태 |
| --- | --- | --- |
| Hardware | ``hardware_rules`` | M4 (M1 데이터 기반) |
| Software | ``software_rules`` | M4 (M1 데이터 기반) |
| Security | ``security_rules`` | M7에서 추가 예정 |
"""

from . import hardware_rules  # noqa: F401
from . import software_rules  # noqa: F401
