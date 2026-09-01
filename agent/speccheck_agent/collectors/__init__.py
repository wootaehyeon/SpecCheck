"""Collector 패키지.

여기서 import 하는 것만 레지스트리에 등록된다. 새 collector를 추가하면
이 파일에 import 한 줄을 더한다. 순서가 곧 스캔 실행 순서다.
"""

from .base import Collector, CollectorResult, iter_collectors, register, registry

# 등록 순서 = 실행 순서 (가벼운 것부터).
# performance는 샘플링 대기가 있어 유일하게 초 단위로 걸리므로 뒤에 둔다.
from . import hardware  # noqa: F401  M1
from . import storage_health  # noqa: F401  M2
from . import reliability  # noqa: F401  M2
from . import performance  # noqa: F401  M2
from . import security  # noqa: F401  M6

__all__ = ["Collector", "CollectorResult", "iter_collectors", "register", "registry"]
