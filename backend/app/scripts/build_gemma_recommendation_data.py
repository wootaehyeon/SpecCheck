"""Export source-grounded synthetic SFT examples in the live Gemma response format.

This prepares data; it does NOT modify Gemma weights. Labels are programmatic,
must be human reviewed before tuning, and do not measure recommendation quality.
"""
import hashlib
import json
from pathlib import Path

from app.diagnosis import diagnose
from app.diagnosis.compatibility_knowledge import load_knowledge, knowledge_version
from app.diagnosis.explainer import (
    RECOMMENDATION_SYSTEM_PROMPT, build_prompt, build_recommendation_prompt,
    _fallback_ui, _select_fallback_candidates,
)
from app.diagnosis.recommendations import build_recommendations
from app.schemas.telemetry import TelemetrySnapshot
from app.services.component_catalog import load_catalog

OUTPUT = Path(__file__).resolve().parents[3] / "datasets/compatibility/gemma"


def example_snapshot(board, scenario):
    storage = scenario.startswith("storage")
    memory = {"total_gb": 32 if storage else 4, "slot_count": board["ram_slots"], "module_count": 1,
              "empty_slot_count": board["ram_slots"] - 1,
              "modules": [{"memory_generation": board["ram_type"], "form_factor": "DIMM"}]}
    if scenario == "memory-unknown-slots":
        memory.pop("slot_count")
        memory.pop("empty_slot_count")
    if scenario == "memory-full-slots":
        memory["empty_slot_count"] = 0
        memory["module_count"] = board["ram_slots"]
    hardware = {"motherboard": {"manufacturer": board["vendor"], "product": board["model"]},
                "memory": memory, "storage": [{"model": "Observed system disk", "media_type": "SSD",
                                              "size_gb": 1000, "bus_type": "SATA" if scenario == "storage-sata" else "NVMe"}]}
    sections = {"hardware": {"status": "ok", "data": hardware}}
    if storage:
        sections["storage_health"] = {"status": "ok", "data": {"disks": [{"model": "Observed system disk", "is_system": True, "predict_failure": True}]}}
    return TelemetrySnapshot.model_validate({"schema_version": "1.1.0", "snapshot_id": "synthetic-training",
        "scan_mode": "actual", "collected_at": "2026-11-18T00:00:00Z",
        "agent": {"version": "synthetic", "os": "Windows"}, "sections": sections})


def build():
    knowledge, revision = load_knowledge()
    catalog, catalog_revision = load_catalog()
    groups = sorted({board["vendor"] + ":" + board["model"].replace(" D4", "") for board in knowledge["boards"]},
                    key=lambda value: hashlib.sha256(value.encode()).hexdigest())
    eval_groups = set(groups[:max(1, len(groups) // 4)])
    output = {"train": [], "eval": []}
    for board in knowledge["boards"]:
        group = board["vendor"] + ":" + board["model"].replace(" D4", "")
        split = "eval" if group in eval_groups else "train"
        for scenario in ("memory", "memory-unknown-slots", "memory-full-slots", "storage-sata", "storage-nvme"):
            snapshot = example_snapshot(board, scenario)
            result = diagnose(snapshot)
            recommendations = build_recommendations(snapshot, result, catalog)
            if not recommendations:
                continue
            selected = _select_fallback_candidates(recommendations)
            overview = _fallback_ui(result, unavailable=False)
            response = {"overview": overview["overview"], "actionPlan": overview["actionPlan"], "recommendations": []}
            for recommendation in selected:
                candidate = next(c for c in recommendation.candidates if c.recommended)
                response["recommendations"].append({"id": recommendation.id, "candidateId": candidate.id,
                    "rationale": recommendation.ai_insight.rationale, "cautions": recommendation.ai_insight.cautions})
            prompt = build_prompt(result) + "\n\n" + build_recommendation_prompt(recommendations) + "\nJSON으로만 답하세요."
            output[split].append({"group_id": group, "scenario": scenario, "source_urls": [board["source"]],
                "label_source": "programmatic_compatibility_checks", "human_reviewed": False,
                "messages": [{"role": "system", "content": RECOMMENDATION_SYSTEM_PROMPT},
                             {"role": "user", "content": prompt},
                             {"role": "assistant", "content": json.dumps(response, ensure_ascii=False)}]})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for split, rows in output.items():
        (OUTPUT / f"{split}.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    manifest = {"knowledge_sha256": revision, "catalog_revision": catalog_revision,
                "attribution": knowledge["attribution"], "weights_trained": False, "human_reviewed": False,
                "split_method": "motherboard family held out; D4 and DDR5 variants share group",
                "counts": {k: len(v) for k, v in output.items()}, "eval_groups": sorted(eval_groups)}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    build()
