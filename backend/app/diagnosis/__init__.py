"""ML diagnosis. Legacy rule registry is retained for offline weak supervision."""

from .engine import Rule, diagnose, register, registry
from . import rules  # noqa: F401  import 시점에 규칙 등록

__all__ = ["Rule", "diagnose", "register", "registry"]
