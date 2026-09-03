"""Convert telemetry/rule output into the UI diagnosis contract."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.schemas.diagnosis import ActionType, DiagnosisResult, Finding, Severity
from app.schemas.telemetry import Section, TelemetrySnapshot
from app.schemas.ui_diagnosis import (
    AiDiagnosis,
    Categories,
    CategorySummary,
    Decision,
    InventoryItem,
    Machine,
    Resource,
    Risk,
    Source,
    UiDiagnosis,
    UiFinding,
)

_SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}
_RISK_BANDS = {
    Severity.INFO: (0, 14),
    Severity.LOW: (15, 39),
    Severity.MEDIUM: (40, 69),
    Severity.HIGH: (70, 84),
    Severity.CRITICAL: (85, 100),
}
_SOURCE_SECTIONS = {
    "wmi": "hardware",
    "cim": "hardware",
    "whea": "reliability",
    "storage": "storage_health",
    "performance": "performance",
    "sysmon": "security",
}


def risk_level(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def score_findings(findings: list[Finding]) -> int:
    """Score within the highest finding's severity band.

    Confidence determines the position inside the band. Additional findings
    raise the score without silently promoting it to a higher severity.
    """
    if not findings:
        return 0
    highest = max(findings, key=lambda item: _SEVERITY_ORDER[item.severity]).severity
    peers = [item for item in findings if item.severity == highest]
    base, ceiling = _RISK_BANDS[highest]
    span = ceiling - base
    confidence = max(item.confidence for item in peers)
    confidence_points = round(span * min(confidence, 1.0) * 0.75)
    frequency_points = min(len(findings) - 1, 5) * max(1, round(span * 0.05))
    return min(ceiling, base + confidence_points + frequency_points)


def _permission_limited(section: Section) -> bool:
    values: list[str] = [section.error or ""]
    values.extend(str(value) for value in section.data.get("collect_errors", []))
    text = " ".join(values).lower()
    hints = ("permission", "access denied", "administrator", "elevated", "권한", "관리자", "거부")
    return any(hint in text for hint in hints)


def _source_status(snapshot: TelemetrySnapshot, section_name: str) -> str:
    section = snapshot.sections.get(section_name)
    if section is None:
        return "not_in_scope" if section_name == "security" else "unavailable"
    if section.status == "planned":
        return "not_in_scope"
    if section.status == "partial":
        return "permission_required" if _permission_limited(section) else "collected"
    if section.status == "ok":
        return "collected"
    return "unavailable"


def _sources(snapshot: TelemetrySnapshot) -> list[Source]:
    collected_at = snapshot.collected_at.isoformat()
    return [
        Source(
            name=name,
            status=(status := _source_status(snapshot, section_name)),
            collectedAt=collected_at if status == "collected" else None,
        )
        for name, section_name in _SOURCE_SECTIONS.items()
    ]


def _diagnosis_status(snapshot: TelemetrySnapshot) -> str:
    required = ("hardware", "storage_health", "reliability", "performance")
    usable = sum(1 for name in required if snapshot.section(name) is not None)
    if usable >= 4:
        return "complete"
    if usable:
        return "partial"
    return "failed"


def _health_status(findings: list[Finding], codes: set[str]) -> str:
    matches = [item for item in findings if item.rule_id in codes]
    if not matches:
        return "normal"
    severity = max(matches, key=lambda item: _SEVERITY_ORDER[item.severity]).severity
    return "critical" if severity in (Severity.HIGH, Severity.CRITICAL) else "warning"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 2)


def _append_resource(
    resources: list[Resource], *, key: str, label: str, value: Any, unit: str, detail: str, status: str
) -> None:
    numeric = _number(value)
    if numeric is not None:
        resources.append(Resource(key=key, label=label, value=numeric, unit=unit, detail=detail, status=status))


def _resources(snapshot: TelemetrySnapshot, findings: list[Finding]) -> list[Resource]:
    performance = snapshot.data("performance")
    storage = snapshot.data("storage_health")
    cpu = performance.get("cpu") or {}
    memory = performance.get("memory") or {}
    disk = performance.get("disk") or {}
    clock = cpu.get("clock") or {}
    resources: list[Resource] = []

    usage = cpu.get("usage_percent") or {}
    _append_resource(
        resources,
        key="cpu_usage",
        label="CPU",
        value=usage.get("avg"),
        unit="%",
        detail="최대 {0}%".format(usage.get("max", "-")),
        status=_health_status(findings, {"PF-CPU-001"}),
    )
    available = memory.get("available_mb") or {}
    _append_resource(
        resources,
        key="memory_available",
        label="사용 가능 메모리",
        value=available.get("avg"),
        unit="MB",
        detail="최소 {0}MB".format(available.get("min", "-")),
        status=_health_status(findings, {"PF-MEM-001"}),
    )
    committed = memory.get("committed_percent") or {}
    _append_resource(
        resources,
        key="memory_committed",
        label="메모리 사용률",
        value=committed.get("avg"),
        unit="%",
        detail="최대 {0}%".format(committed.get("max", "-")),
        status=_health_status(findings, {"PF-MEM-001"}),
    )
    queue = disk.get("queue_length") or {}
    _append_resource(
        resources,
        key="disk_queue",
        label="디스크 대기열",
        value=queue.get("avg"),
        unit="",
        detail="최대 {0}".format(queue.get("max", "-")),
        status="normal",
    )
    volumes = storage.get("volumes") or []
    system_volume = next((item for item in volumes if item.get("is_system")), {})
    _append_resource(
        resources,
        key="system_free_space",
        label="시스템 드라이브 여유",
        value=system_volume.get("free_percent"),
        unit="%",
        detail="{0}GB 여유".format(system_volume.get("free_gb", "-")),
        status=_health_status(findings, {"ST-SPACE-001"}),
    )
    _append_resource(
        resources,
        key="cpu_clock",
        label="CPU 동작 클럭",
        value=clock.get("current_mhz"),
        unit="MHz",
        detail="정격 {0}MHz".format(clock.get("max_mhz", "-")),
        status=_health_status(findings, {"PF-THROTTLE-001"}),
    )
    return resources


def _item_status(findings: list[Finding], prefixes: tuple[str, ...]) -> str:
    relevant = [item for item in findings if item.rule_id.startswith(prefixes)]
    if not relevant:
        return "normal"
    severity = max(relevant, key=lambda item: _SEVERITY_ORDER[item.severity]).severity
    return "critical" if severity in (Severity.HIGH, Severity.CRITICAL) else "warning"


def _inventory(snapshot: TelemetrySnapshot, findings: list[Finding]) -> list[InventoryItem]:
    hardware = snapshot.data("hardware")
    items: list[InventoryItem] = []
    for cpu in hardware.get("cpu") or []:
        items.append(InventoryItem(
            kind="CPU", name=cpu.get("name") or "알 수 없는 CPU",
            detail="{0}코어 / {1}스레드 · 최대 {2}MHz".format(cpu.get("cores", "-"), cpu.get("threads", "-"), cpu.get("max_clock_mhz", "-")),
            status=_item_status(findings, ("PF-CPU", "PF-THROTTLE")),
        ))
    for gpu in hardware.get("gpu") or []:
        vram = gpu.get("adapter_ram_gb")
        vram_detail = "{0}GB VRAM".format(vram) if vram is not None else "VRAM 확인 불가"
        items.append(InventoryItem(
            kind="GPU", name=gpu.get("name") or "알 수 없는 GPU",
            detail="{0} · 드라이버 {1}".format(vram_detail, gpu.get("driver_version", "-")),
            status=_item_status(findings, ("SW-GPU",)),
        ))
    memory = hardware.get("memory") or {}
    if memory:
        modules = memory.get("modules") or []
        configured = next((item.get("configured_speed_mhz") for item in modules if item.get("configured_speed_mhz")), None)
        items.append(InventoryItem(
            kind="Memory", name="메모리 {0}GB".format(memory.get("total_gb", "-")),
            detail="{0}개 모듈 · {1}MHz".format(memory.get("module_count", len(modules)), configured or "-"),
            status=_item_status(findings, ("HW-RAM", "PF-MEM")),
        ))
    for disk in hardware.get("storage") or []:
        items.append(InventoryItem(
            kind="Storage", name=disk.get("model") or "알 수 없는 저장장치",
            detail="{0} · {1} · {2}GB".format(disk.get("media_type") or "Unknown", disk.get("bus_type") or disk.get("interface") or "-", disk.get("size_gb", "-")),
            status=_item_status(findings, ("HW-DISK", "ST-", "RL-DISK")),
        ))
    board = hardware.get("motherboard") or {}
    if board:
        bios = board.get("bios") or {}
        items.append(InventoryItem(
            kind="Motherboard", name=" ".join(filter(None, [board.get("manufacturer"), board.get("product")])) or "알 수 없는 메인보드",
            detail="BIOS {0}".format(bios.get("version") or "-"),
            status=_item_status(findings, ("SW-BIOS",)),
        ))
    return items


def _category(findings: list[Finding], axis: str, diagnosis_status: str) -> CategorySummary:
    selected = [item for item in findings if item.axis.value == axis]
    highest = max(selected, key=lambda item: _SEVERITY_ORDER[item.severity]).severity if selected else Severity.INFO
    labels = {"hardware": "하드웨어", "software": "소프트웨어", "security": "보안"}
    if selected:
        summary = "{0} 점검 항목 {1}건".format(labels[axis], len(selected))
    elif axis == "security":
        summary = "Basic Scan 범위 밖"
    elif diagnosis_status == "failed":
        summary = "수집 데이터가 없어 판정하지 못함"
    else:
        summary = "확인된 범위에서 감지된 이상 없음"
    return CategorySummary(count=len(selected), highestSeverity=highest, summary=summary)


def _findings(findings: Iterable[Finding]) -> list[UiFinding]:
    return [
        UiFinding(
            id=item.rule_id,
            category=item.axis,
            code=item.rule_id,
            title=item.title,
            severity=item.severity,
            confidence=item.confidence,
            summary=item.summary,
            evidence=[evidence.detail for evidence in item.evidence],
            rootCauseCandidates=[item.root_cause] if item.root_cause else [],
            actions=[item.action_detail] if item.action_detail else [],
            recommendedAction=item.recommended_action,
        )
        for item in findings
    ]


def to_ui_diagnosis(snapshot: TelemetrySnapshot, result: DiagnosisResult, ai: dict[str, Any]) -> UiDiagnosis:
    findings = result.findings
    score = score_findings(findings)
    status = _diagnosis_status(snapshot)
    hardware = snapshot.data("hardware")
    os_data = hardware.get("os") or {}
    os_name = os_data.get("caption") or snapshot.agent.os
    build = os_data.get("build") or snapshot.agent.os_version
    if build and str(build) not in str(os_name):
        os_name = "{0} {1}".format(os_name, build)

    return UiDiagnosis(
        scanId=snapshot.snapshot_id,
        status=status,
        generatedAt=result.generated_at.isoformat(),
        machine=Machine(
            name=(snapshot.device_id or "unknown-device")[:12],
            os=os_name,
            agentVersion=snapshot.agent.version,
        ),
        risk=Risk(score=score, level=risk_level(score), summary=result.decision.reason),
        categories=Categories(
            hardware=_category(findings, "hardware", status),
            software=_category(findings, "software", status),
            security=_category(findings, "security", status),
        ),
        resources=_resources(snapshot, findings),
        findings=_findings(findings),
        inventory=_inventory(snapshot, findings),
        sources=_sources(snapshot),
        ai=AiDiagnosis.model_validate(ai),
        decision=Decision(
            action=result.decision.action,
            reason=result.decision.reason,
            drivenBy=result.decision.driven_by,
        ),
    )
