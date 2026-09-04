"""Turn confirmed purchase findings into conservative replacement suggestions.

The rule engine decides *whether* a purchase is warranted.  This module only
names a replacement category when the telemetry supports it; it never invents
a price or a specific retail listing.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from app.schemas.diagnosis import ActionType, DiagnosisResult, Finding, Severity
from app.schemas.telemetry import TelemetrySnapshot
from app.schemas.ui_diagnosis import Recommendation


_PRIORITY = {
    Severity.CRITICAL: "urgent",
    Severity.HIGH: "high",
    Severity.MEDIUM: "normal",
    Severity.LOW: "normal",
    Severity.INFO: "normal",
}
_STORAGE_RULES = {"HW-DISK-001", "ST-SMART-001", "ST-SMART-002", "ST-WEAR-001", "RL-DISK-001"}
_MEMORY_RULES = {"HW-RAM-002", "PF-MEM-001"}


def _system_disk_size(snapshot: TelemetrySnapshot) -> int | None:
    for disk in snapshot.data("storage_health").get("disks") or []:
        if disk.get("is_system") and isinstance(disk.get("size_gb"), (int, float)):
            return int(disk["size_gb"])
    for volume in snapshot.data("storage_health").get("volumes") or []:
        if volume.get("is_system") and isinstance(volume.get("size_gb"), (int, float)):
            return int(volume["size_gb"])
    for disk in snapshot.data("hardware").get("storage") or []:
        if isinstance(disk.get("size_gb"), (int, float)):
            return int(disk["size_gb"])
    return None


def _storage_recommendation(finding: Finding, snapshot: TelemetrySnapshot) -> Recommendation:
    current_size = _system_disk_size(snapshot)
    capacity = max(1000, current_size or 0)
    query = "NVMe SSD {0}GB".format(capacity)
    return Recommendation(
        id="storage-replacement",
        findingIds=[finding.rule_id],
        priority=_PRIORITY[finding.severity],
        category="storage",
        title="시스템용 NVMe SSD 교체 검토",
        description=(
            "{0}의 근거로 시스템 저장장치 교체가 필요합니다. 현재 용량을 유지하거나 "
            "여유를 고려해 {1}GB 이상을 우선 검토하세요."
        ).format(finding.title, capacity),
        searchQuery=query,
        searchUrl="https://search.shopping.naver.com/search/all?query={0}".format(quote_plus(query)),
    )


def _memory_recommendation(finding: Finding, snapshot: TelemetrySnapshot) -> Recommendation:
    memory = snapshot.data("hardware").get("memory") or {}
    current = memory.get("total_gb")
    current_gb = int(current) if isinstance(current, (int, float)) else 0
    target = max(16, current_gb * 2)
    modules = memory.get("modules") or []
    speed = next((item.get("rated_speed_mhz") for item in modules if item.get("rated_speed_mhz")), None)
    query = "{0}GB PC 메모리{1}".format(target, " {0}MHz".format(speed) if speed else "")
    return Recommendation(
        id="memory-upgrade",
        findingIds=[finding.rule_id],
        priority=_PRIORITY[finding.severity],
        category="memory",
        title="메모리 {0}GB 이상 증설 검토".format(target),
        description=(
            "{0}의 근거로 물리 메모리 증설을 우선 검토하세요. 구매 전 메인보드의 "
            "DDR 세대와 빈 슬롯을 확인해야 합니다."
        ).format(finding.title),
        searchQuery=query,
        searchUrl="https://search.shopping.naver.com/search/all?query={0}".format(quote_plus(query)),
    )


def build_recommendations(snapshot: TelemetrySnapshot, result: DiagnosisResult) -> list[Recommendation]:
    """Return deduplicated, evidence-backed purchase suggestions.

    Findings marked ``fix`` and ``keep`` intentionally cannot enter this path.
    Purchase findings without a safely mappable component remain visible as a
    finding, rather than being converted into a misleading product suggestion.
    """
    suggestions: dict[str, Recommendation] = {}
    for finding in result.findings:
        if finding.recommended_action is not ActionType.PURCHASE:
            continue
        if finding.rule_id in _STORAGE_RULES:
            candidate = _storage_recommendation(finding, snapshot)
        elif finding.rule_id in _MEMORY_RULES:
            candidate = _memory_recommendation(finding, snapshot)
        else:
            continue

        existing = suggestions.get(candidate.id)
        if existing is None:
            suggestions[candidate.id] = candidate
        else:
            existing.finding_ids.append(finding.rule_id)

    return sorted(suggestions.values(), key=lambda item: (item.priority != "urgent", item.priority != "high", item.id))
