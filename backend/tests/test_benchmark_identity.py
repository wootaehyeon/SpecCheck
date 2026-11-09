"""Unknown parts must never inherit another model's score, price or power."""

import pytest

from app.logic.compatibility import _find_component
from app.logic import evaluator


@pytest.mark.parametrize("query,expected", [
    ("NVIDIA GeForce RTX 3090", "GeForce RTX 3090"),
    ("RTX 3090 Ti", "GeForce RTX 3090 Ti"),
    ("Intel(R) Core(TM) i7-12700", "Intel Core i7-12700"),
    ("GeForce RTX 4060", None),
    ("RTX 3090 Ti 24GB", None),
    ("RTX 3090 Laptop GPU", None),
    ("Intel Core i7-12700KF", None),
    ("Core i7", None),
    (None, None),
])
def test_benchmark_matching_preserves_model_and_variant(query, expected):
    benchmark = {name: {"score": 100} for name in [
        "GeForce RTX 3090 Ti", "GeForce RTX 3090", "Intel Core i7-12700K", "Intel Core i7-12700",
    ]}
    assert _find_component(benchmark, query)[0] == expected


def test_unknown_gpu_is_not_scored_or_priced(monkeypatch):
    monkeypatch.setattr(evaluator, "_load", lambda _: {"GeForce RTX 3090 Ti": {"score": 29094}})
    monkeypatch.setattr(evaluator, "get_price", lambda _: pytest.fail("Unknown parts must not request another model's price"))
    result = evaluator.evaluate_build({"cpu": None, "gpu": "GeForce RTX 4060"})
    assert result["cpu_matched"] is None
    assert result["gpu_matched"] is None
    assert result["gpu_score"] == 0
    assert result["gpu_price_krw"] is None
