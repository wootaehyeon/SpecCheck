"""Create compatibility-checked minimal and platform replacement candidates."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote_plus

from app.logic.compatibility import check_compatibility, infer_board_socket, infer_cpu_socket, infer_memory_generation
from app.schemas.diagnosis import ActionType, DiagnosisResult, Finding, Severity
from app.schemas.telemetry import TelemetrySnapshot
from app.schemas.ui_diagnosis import CandidatePart, CompatibilityCheck, Recommendation, ReplacementCandidate

_PRIORITY = {Severity.CRITICAL: "urgent", Severity.HIGH: "high", Severity.MEDIUM: "normal", Severity.LOW: "normal", Severity.INFO: "normal"}
_STORAGE_RULES = {"HW-DISK-001", "ST-SMART-001", "ST-SMART-002", "ST-WEAR-001", "RL-DISK-001"}
_MEMORY_RULES = {"HW-RAM-002", "PF-MEM-001"}
_PLATFORM_CATALOG = Path(__file__).resolve().parents[2] / "data" / "replacement_platforms.json"


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


def _part(candidate_id: str, category: str, name: str, reason: str) -> CandidatePart:
    return CandidatePart(key=f"{candidate_id}-{category}", category=category, name=name, searchQuery=name, reason=reason)


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
    spec = " ".join(filter(None, [generation, f"{target}GB", f"{speed}MHz" if speed else None, "메모리"]))
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
        candidate_id="memory-minimal", strategy="minimal", title="최소 교체: 메모리만 증설",
        summary="현재 CPU와 메인보드를 유지하고 메모리 용량 부족만 해결합니다.", recommended=True,
        parts=[_part("memory-minimal", "memory", spec, "물리 메모리 부족을 직접 해소")], checks=checks,
        tradeoffs=["교체 부품과 비용이 가장 적음", "현재 CPU·메인보드의 성능 한계는 유지"],
        build={"cpu": _cpu_name(snapshot), "gpu": None, "motherboard": _board_name(snapshot), "ram": spec,
               "psu_watt": None, "storage": [], "use_case": None},
    )


def _select_platform(snapshot: TelemetrySnapshot) -> dict:
    profiles = json.loads(_PLATFORM_CATALOG.read_text(encoding="utf-8"))
    current_cpu = _cpu_name(snapshot).lower()
    current_vendor = "amd" if "amd" in current_cpu or "ryzen" in current_cpu else "intel" if "intel" in current_cpu else None
    current_socket = infer_cpu_socket(_cpu_name(snapshot)) or infer_board_socket(_board_name(snapshot))
    candidates = [profile for profile in profiles if profile["socket"] != current_socket]
    preferred = [profile for profile in candidates if profile["vendor"] == current_vendor]
    return min(preferred or candidates or profiles, key=lambda profile: profile["priority"])


def _platform_bundle(snapshot: TelemetrySnapshot, reason: str) -> ReplacementCandidate | None:
    profile = _select_platform(snapshot)
    candidate_id = profile["id"]
    parts = [
        _part(candidate_id, "cpu", profile["cpu"], "플랫폼 카탈로그의 보급형 CPU 후보"),
        _part(candidate_id, "motherboard", profile["motherboard"], "CPU 소켓과 메모리 규격을 함께 전환"),
        _part(candidate_id, "memory", profile["memory"], "신규 플랫폼에 맞는 메모리 구성"),
    ]
    current_socket = infer_cpu_socket(_cpu_name(snapshot)) or infer_board_socket(_board_name(snapshot))
    return _verified_candidate(
        candidate_id=candidate_id, strategy="platform", title=profile["title"],
        summary="CPU·메인보드·RAM을 함께 바꿔 향후 업그레이드 경로를 확보합니다.", recommended=False,
        parts=parts,
        checks=[
            CompatibilityCheck(label="CPU 소켓", status="passed", detail=f"CPU와 메인보드는 {profile['socket']} 소켓으로 일치합니다."),
            CompatibilityCheck(label="메모리 세대", status="passed", detail=f"메인보드와 메모리는 {profile['memory_generation']} 규격으로 일치합니다."),
            CompatibilityCheck(label="케이스·파워", status="conditional", detail="케이스 규격과 PSU 용량은 WMI에서 확인할 수 없어 구매 전에 확인해야 합니다."),
        ],
        tradeoffs=[profile["upgrade_path"], "최소 교체안보다 비용과 작업 범위가 큼", reason,
                   f"현재 플랫폼: {current_socket or '확인 불가'}"],
        build={"cpu": profile["cpu"], "gpu": None, "motherboard": profile["motherboard"],
               "ram": profile["memory"], "psu_watt": None,
               "storage": [{"type": "NVMe", "capacity_gb": 1000}], "use_case": None},
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
    name = f"{interface or '내장'} SSD {capacity}GB"
    minimal = _verified_candidate(
        candidate_id="storage-minimal", strategy="minimal", title="최소 교체: 저장장치만 교체",
        summary="현재 플랫폼을 유지하고 문제가 확인된 저장장치만 같은 인터페이스로 교체합니다.", recommended=True,
        parts=[_part("storage-minimal", "storage", name, "고장 위험 또는 성능 병목이 확인된 디스크를 교체")],
        checks=[CompatibilityCheck(
            label="저장장치 인터페이스", status="passed" if interface else "conditional",
            detail=(f"현재 시스템 디스크의 {interface} 인터페이스와 같은 규격을 선택했습니다."
                    if interface else "현재 인터페이스가 확인되지 않아 SATA/NVMe 지원 여부를 구매 전에 확인해야 합니다."),
        )], tradeoffs=["문제 부품만 교체해 비용을 최소화", "OS와 데이터 마이그레이션 필요"],
        build={"cpu": _cpu_name(snapshot), "gpu": None, "motherboard": _board_name(snapshot), "ram": None,
               "psu_watt": None, "storage": [{"type": interface or "SSD", "capacity_gb": capacity}],
               "existing_storage": [
                   {"type": item.get("bus_type") or item.get("interface") or item.get("media_type")}
                   for item in (_hardware(snapshot).get("storage") or [])
               ], "use_case": None},
    )
    platform = _platform_bundle(snapshot, "저장장치 이상만으로는 플랫폼 전체 교체 근거가 부족함")
    return [candidate for candidate in (minimal, platform) if candidate is not None]


def _recommendation(finding: Finding, snapshot: TelemetrySnapshot) -> Recommendation | None:
    if finding.rule_id in _MEMORY_RULES:
        memory = _hardware(snapshot).get("memory") or {}
        target = max(16, int(memory.get("total_gb") or 0) * 2)
        candidates = [candidate for candidate in (
            _minimal_memory(snapshot, target),
            _platform_bundle(snapshot, "메모리 부족만으로는 플랫폼 전체 교체 근거가 부족함"),
        ) if candidate is not None]
        category, title = "memory", "메모리 교체 범위 비교"
    elif finding.rule_id in _STORAGE_RULES:
        candidates = _storage_candidates(snapshot)
        category, title = "storage", "저장장치 교체 범위 비교"
    else:
        return None
    query = candidates[0].parts[0].search_query if candidates else f"{category} replacement"
    return Recommendation(
        id=f"{category}-recommendation", findingIds=[finding.rule_id], priority=_PRIORITY[finding.severity],
        category=category, title=title, description=finding.summary, searchQuery=query,
        searchUrl="https://search.shopping.naver.com/search/all?query={0}".format(quote_plus(query)),
        candidates=candidates,
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
