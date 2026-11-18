"""Hardware constraints and Gemma grounding regressions; no LLM/network required."""
import json
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.diagnosis import diagnose, explainer
from app.diagnosis.compatibility_knowledge import board_for, lookup, memory_facts, memory_candidate_allowed
from app.diagnosis.recommendations import build_recommendations
from app.schemas.telemetry import TelemetrySnapshot


def snapshot(board="PRIME B760-PLUS D4", modules=None, **memory):
    return TelemetrySnapshot.model_validate({"schema_version": "1.1.0", "snapshot_id": "grounding-test",
        "collected_at": "2026-11-18T00:00:00Z", "scan_mode": "actual", "agent": {"version": "test", "os": "Windows"},
        "sections": {"hardware": {"status": "ok", "data": {
            "motherboard": {"manufacturer": "ASUSTeK COMPUTER INC.", "product": board},
            "memory": {"total_gb": 4, "modules": modules or [], **memory}}}}})


def product(**values):
    return {"memory_generation": "DDR4", "module_count": 2, "capacity_gb": 32, "form_factor": "UDIMM", **values}


def test_exact_board_variant_and_unknown_model():
    assert board_for(snapshot())["ram_type"] == "DDR4"
    assert board_for(snapshot("PRIME B760-PLUS"))["ram_type"] == "DDR5"
    assert board_for(snapshot("PRIME B760-PLUS D4 WIFI UNKNOWN")) is None
    assert lookup("boards", "B760") is None


def test_vendor_mismatch_does_not_borrow_another_board_spec():
    data = snapshot()
    data.sections["hardware"].data["motherboard"]["manufacturer"] = "Other vendor"
    assert board_for(data) is None


def test_fast_ddr4_is_not_invented_as_ddr5():
    data = snapshot("Unknown OEM", [{"rated_speed_mhz": 5000}])
    assert memory_facts(data)["generation"] is None
    data.sections["hardware"].data["memory"]["modules"][0]["smbios_memory_type"] = 26
    assert memory_facts(data)["generation"] == "DDR4"


@pytest.mark.parametrize("changes", [
    {"memory_generation": "DDR5"}, {"capacity_gb": 256}, {"module_count": 8}, {"form_factor": "SODIMM"},
])
def test_incompatible_memory_never_enters_candidate_pool(changes):
    assert not memory_candidate_allowed(snapshot(), product(**changes))


def test_observed_ddr5_on_unknown_board_and_conflicting_evidence():
    data = snapshot("B660M HD3P", [{"smbios_memory_type": 34, "form_factor": "DIMM"}])
    assert memory_candidate_allowed(data, product(memory_generation="DDR5"))
    assert not memory_candidate_allowed(data, product())
    contradictory = snapshot(modules=[{"smbios_memory_type": 34}])
    assert memory_facts(contradictory)["conflict"]
    assert not build_recommendations(contradictory, diagnose(contradictory))


def test_sodimm_machine_rejects_desktop_dimm():
    data = snapshot("Unknown OEM", [{"memory_generation": "DDR4", "form_factor": "SODIMM"}])
    assert not memory_candidate_allowed(data, product())


def mocked_gemma(monkeypatch, rationale="현재 사양을 기준으로 선택했습니다.", overview="용량이 부족합니다."):
    data = snapshot()
    result = diagnose(data)
    recommendations = build_recommendations(data, result)
    selected = recommendations[0].candidates[-1]
    monkeypatch.setattr(get_settings(), "llm_enabled", True)
    monkeypatch.setattr(explainer, "ollama_status", lambda: {"available": True, "installed": True, "model": "mock-gemma"})
    monkeypatch.setattr(explainer, "_ask_ollama_bundle_json", lambda *args, **kwargs: {
        "overview": overview, "actionPlan": ["확인하세요."], "recommendations": [{
            "id": recommendations[0].id, "candidateId": selected.id, "rationale": rationale, "cautions": [],
        }],
    })
    return result, recommendations, selected


def test_gemma_cannot_omit_checks_or_leave_search_link_pointing_to_old_candidate(monkeypatch):
    result, recommendations, selected = mocked_gemma(monkeypatch)
    _, enriched = explainer.explain_for_ui_bundle(result, recommendations)
    mandatory = {c.detail for c in selected.checks if c.status == "conditional"}
    assert mandatory <= set(enriched[0].ai_insight.cautions)
    assert enriched[0].search_query == selected.parts[0].search_query
    assert next(c for c in enriched[0].candidates if c.recommended).id == selected.id


@pytest.mark.parametrize("field", ["rationale", "overview"])
def test_unfounded_compatibility_guarantees_fall_back(monkeypatch, field):
    result, recommendations, _ = mocked_gemma(monkeypatch, **{field: "100% 호환됩니다. 확인이 필요 없습니다."})
    _, enriched = explainer.explain_for_ui_bundle(result, recommendations)
    assert enriched[0].ai_insight.provider == "template"
    assert enriched[0].ai_insight.cautions


def test_prompt_contains_retrieved_sources_and_observed_pc():
    data = snapshot()
    text = explainer.build_recommendation_prompt(build_recommendations(data, diagnose(data)))
    assert "prime-b760-plus-d4/techspec/" in text
    assert "현재 PC 구성" in text
    assert "사양 출처:" in text


def test_sft_examples_are_disjoint_and_match_live_response_contract():
    root = Path(__file__).resolve().parents[2] / "datasets/compatibility/gemma"
    splits = {key: [json.loads(line) for line in (root / f"{key}.jsonl").read_text(encoding="utf-8").splitlines()]
              for key in ("train", "eval")}
    assert {r["group_id"] for r in splits["train"]}.isdisjoint({r["group_id"] for r in splits["eval"]})
    for row in splits["train"] + splits["eval"]:
        assert row["human_reviewed"] is False
        answer = json.loads(row["messages"][-1]["content"])
        assert answer["overview"] and answer["actionPlan"]
        for item in answer["recommendations"]:
            assert f"candidateId: {item['candidateId']} |" in row["messages"][1]["content"]
            assert item["cautions"]
