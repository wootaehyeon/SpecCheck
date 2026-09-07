"""Create compatibility-checked replacement candidates for detected faults."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from app.logic.compatibility import check_compatibility, infer_board_socket, infer_memory_generation
from app.schemas.diagnosis import ActionType, DiagnosisResult, Finding, Severity
from app.schemas.telemetry import TelemetrySnapshot
from app.schemas.ui_diagnosis import (
    CandidatePart,
    CompatibilityCheck,
    Recommendation,
    RecommendationAiInsight,
    ReplacementCandidate,
)

_PRIORITY = {Severity.CRITICAL: "urgent", Severity.HIGH: "high", Severity.MEDIUM: "normal", Severity.LOW: "normal", Severity.INFO: "normal"}
_STORAGE_RULES = {"HW-DISK-001", "ST-SMART-001", "ST-SMART-002", "ST-WEAR-001", "RL-DISK-001"}
_MEMORY_RULES = {"HW-RAM-002", "PF-MEM-001"}
_COMPONENT_CATALOG = Path(__file__).resolve().parents[2] / "data" / "component_catalog.json"


def _hardware(snapshot: TelemetrySnapshot) -> dict:
    return snapshot.data("hardware")


def _board_name(snapshot: TelemetrySnapshot) -> str:
    board = _hardware(snapshot).get("motherboard") or {}
    return " ".join(filter(None, [board.get("manufacturer"), board.get("product")]))


def _cpu_name(snapshot: TelemetrySnapshot) -> str:
    cpus = _hardware(snapshot).get("cpu") or []
    return cpus[0].get("name") if cpus else ""


def _memory_generation(snapshot: TelemetrySnapshot) -> str | None:
    generation = infer_memory_generation(_board_name(snapshot))
    if generation:
        return generation
    modules = (_hardware(snapshot).get("memory") or {}).get("modules") or []
    speed = next((item.get("rated_speed_mhz") for item in modules if item.get("rated_speed_mhz")), None)
    if isinstance(speed, (int, float)):
        return "DDR5" if speed >= 4800 else "DDR4" if speed <= 3600 else None
    return None


@lru_cache(maxsize=1)
def _catalog_products() -> list[dict]:
    """Load only curated products with an official specification source."""
    payload = json.loads(_COMPONENT_CATALOG.read_text(encoding="utf-8"))
    return sorted(
        [item for item in payload.get("products", []) if item.get("id") and item.get("source_url")],
        key=lambda item: int(item.get("selection_priority") or 50),
    )


def _catalog_part(product: dict, reason: str) -> CandidatePart:
    return CandidatePart(
        key=product["id"],
        category=product["category"],
        name=product["name"],
        searchQuery=product["search_query"],
        reason=reason,
        specifications=product.get("specifications", []),
        sourceLabel=product.get("source_label"),
        sourceUrl=product.get("source_url"),
    )


def _verified_candidate(*, candidate_id: str, strategy: str, title: str, summary: str,
                        recommended: bool, parts: list[CandidatePart], checks: list[CompatibilityCheck],
                        tradeoffs: list[str], build: dict) -> ReplacementCandidate | None:
    verification = check_compatibility(build)
    if any(issue["type"] == "error" for issue in verification["issues"]):
        return None
    for issue in verification["issues"]:
        if issue["type"] == "warning":
            checks.append(CompatibilityCheck(
                label=issue["component"], status="conditional", detail=issue["message"]
            ))
    checks.append(CompatibilityCheck(
        label="통합 호환성 검사", status="passed",
        detail="CPU 소켓, 메모리 세대, 저장장치 인터페이스 검사에서 충돌이 없습니다.",
    ))
    conditional_count = sum(check.status == "conditional" for check in checks)
    status = "conditional" if conditional_count else "passed"
    return ReplacementCandidate(
        id=candidate_id, strategy=strategy, title=title, summary=summary, recommended=recommended,
        compatibilityStatus=status, compatibilityScore=max(60, 100 - conditional_count * 15),
        checks=checks, parts=parts, tradeoffs=tradeoffs,
    )


def _minimal_memory(snapshot: TelemetrySnapshot, target: int) -> ReplacementCandidate | None:
    memory = _hardware(snapshot).get("memory") or {}
    generation = _memory_generation(snapshot)
    empty_slots = memory.get("empty_slot_count")
    speed = next((item.get("rated_speed_mhz") for item in memory.get("modules") or [] if item.get("rated_speed_mhz")), None)
    products = [
        product for product in _catalog_products()
        if product.get("category") == "memory"
        and (not generation or product.get("memory_generation") == generation)
        and int(product.get("capacity_gb") or 0) >= target
    ]
    if not products:
        return None
    product = products[0]
    checks = [CompatibilityCheck(
        label="메모리 규격", status="passed" if generation else "conditional",
        detail=(f"현재 플랫폼이 {generation}로 확인돼 같은 세대 후보만 선택했습니다."
                if generation else "DDR 세대를 확인하지 못해 구매 전 메인보드 사양 확인이 필요합니다."),
    ), CompatibilityCheck(
        label="장착 방식", status="passed" if isinstance(empty_slots, int) else "conditional",
        detail=(f"빈 슬롯 {empty_slots}개를 사용해 증설할 수 있습니다." if isinstance(empty_slots, int) and empty_slots > 0
                else "빈 슬롯이 없어 기존 모듈을 키트로 교체합니다." if empty_slots == 0
                else "전체 슬롯 수가 수집되지 않아 설치 전에 빈 슬롯을 확인해야 합니다."),
    )]
    return _verified_candidate(
        candidate_id=product["id"], strategy="minimal", title=product["name"],
        summary="현재 CPU와 메인보드를 유지하고 메모리 용량 부족만 해결하는 카탈로그 후보입니다.", recommended=True,
        parts=[_catalog_part(product, "수집된 메모리 세대와 필요 용량 조건에 맞는 실제 제품")], checks=checks,
        tradeoffs=["문제 부품만 교체해 비용을 최소화", "메모리 모듈 규격과 빈 슬롯은 장착 전에 다시 확인 필요"],
        build={"cpu": _cpu_name(snapshot), "gpu": None, "motherboard": _board_name(snapshot),
               "ram": product["specifications"][0], "psu_watt": None, "storage": [], "use_case": None},
    )


def _system_disk(snapshot: TelemetrySnapshot) -> dict:
    health_disks = snapshot.data("storage_health").get("disks") or []
    inventory_disks = _hardware(snapshot).get("storage") or []
    health_disk = next((disk for disk in health_disks if disk.get("is_system")), None)
    if health_disk is None:
        return inventory_disks[0] if inventory_disks else {}

    model = str(health_disk.get("model") or "").strip().lower()
    inventory_disk = next(
        (disk for disk in inventory_disks if str(disk.get("model") or "").strip().lower() == model),
        None,
    )
    return {**(inventory_disk or {}), **health_disk}


def _storage_candidates(snapshot: TelemetrySnapshot) -> list[ReplacementCandidate]:
    disk = _system_disk(snapshot)
    capacity = max(1000, int(disk.get("size_gb") or 0))
    bus = str(disk.get("bus_type") or disk.get("interface") or "").upper()
    interface = "NVMe" if "NVME" in bus else "SATA" if "SATA" in bus or "IDE" in bus else None
    products = [
        product for product in _catalog_products()
        if product.get("category") == "storage"
        and (not interface or product.get("interface") == interface)
        and int(product.get("capacity_gb") or 0) >= capacity
    ]
    candidates: list[ReplacementCandidate] = []
    for product in products:
        candidate = _verified_candidate(
            candidate_id=product["id"], strategy="minimal", title=product["name"],
            summary="현재 플랫폼을 유지하고 문제가 확인된 저장장치만 교체하는 카탈로그 후보입니다.", recommended=not candidates,
            parts=[_catalog_part(product, "수집된 저장장치 인터페이스와 최소 용량 조건에 맞는 실제 제품")],
            checks=[
                CompatibilityCheck(label="제품 정보 출처", status="passed", detail=f"{product['source_label']}에 등록된 모델입니다."),
                CompatibilityCheck(
                    label="저장장치 인터페이스", status="passed" if interface else "conditional",
                    detail=(f"현재 시스템 디스크의 {interface} 인터페이스 조건과 일치합니다."
                            if interface else "현재 인터페이스를 확인하지 못해 NVMe M.2 슬롯 지원 여부를 구매 전에 확인해야 합니다."),
                ),
                CompatibilityCheck(label="물리 규격", status="conditional", detail=f"{product['form_factor']} 규격입니다. 메인보드 또는 노트북의 실제 슬롯 길이와 방열판 간섭을 구매 전에 확인해야 합니다."),
                CompatibilityCheck(label="용량", status="passed", detail=f"현재 시스템 디스크 {capacity}GB 이상인 {product['capacity_gb']}GB 모델입니다."),
            ], tradeoffs=["문제 부품만 교체해 비용을 최소화", "OS와 데이터 마이그레이션 필요"],
            build={"cpu": _cpu_name(snapshot), "gpu": None, "motherboard": _board_name(snapshot), "ram": None,
                   "psu_watt": None, "storage": [{"type": interface or "SSD", "capacity_gb": product["capacity_gb"]}],
                   "existing_storage": [
                       {"type": item.get("bus_type") or item.get("interface") or item.get("media_type")}
                       for item in (_hardware(snapshot).get("storage") or [])
                   ], "use_case": None},
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _recommendation(finding: Finding, snapshot: TelemetrySnapshot) -> Recommendation | None:
    if finding.rule_id in _MEMORY_RULES:
        memory = _hardware(snapshot).get("memory") or {}
        target = max(16, int(memory.get("total_gb") or 0) * 2)
        candidates = [candidate for candidate in (_minimal_memory(snapshot, target),) if candidate is not None]
        category, title = "memory", "호환 메모리 증설 제안"
    elif finding.rule_id in _STORAGE_RULES:
        candidates = _storage_candidates(snapshot)
        category, title = "storage", "호환 저장장치 교체 제안"
    else:
        return None
    if not candidates:
        return None
    query = candidates[0].parts[0].search_query if candidates else f"{category} replacement"
    recommended = candidates[0]
    cautions = [
        check.detail
        for check in recommended.checks
        if check.status == "conditional"
    ][:3]
    if not cautions:
        cautions = recommended.tradeoffs[-2:]
    return Recommendation(
        id=f"{category}-recommendation", findingIds=[finding.rule_id], priority=_PRIORITY[finding.severity],
        category=category, title=title, description=finding.summary, searchQuery=query,
        searchUrl="https://search.shopping.naver.com/search/all?query={0}".format(quote_plus(query)),
        candidates=candidates,
        aiInsight=RecommendationAiInsight(
            provider="template",
            model="deterministic-ko-v1",
            status="fallback",
            rationale=(
                f"{finding.title}에 대응하면서 현재 부품을 최대한 유지하는 선택입니다. "
                f"우선 후보는 {recommended.title}입니다."
            ),
            cautions=cautions,
        ),
    )


def build_recommendations(snapshot: TelemetrySnapshot, result: DiagnosisResult) -> list[Recommendation]:
    suggestions: dict[str, Recommendation] = {}
    for finding in result.findings:
        if finding.recommended_action is not ActionType.PURCHASE:
            continue
        candidate = _recommendation(finding, snapshot)
        if candidate is None:
            continue
        existing = suggestions.get(candidate.id)
        if existing is None:
            suggestions[candidate.id] = candidate
        else:
            existing.finding_ids.append(finding.rule_id)
    return sorted(suggestions.values(), key=lambda item: (item.priority != "urgent", item.priority != "high", item.id))
