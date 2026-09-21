"""Convert telemetry/rule output into the UI diagnosis contract."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.schemas.diagnosis import ActionType, DiagnosisResult, Finding, Severity
from app.schemas.telemetry import Section, TelemetrySnapshot
from app.schemas.ui_diagnosis import (
    AiDiagnosis,
    AnomalyAnalysis,
    AnomalySignal,
    Categories,
    CategorySummary,
    Decision,
    InventoryItem,
    Machine,
    Resource,
    Risk,
    Recommendation,
    RootCauseCandidate,
    TrajectoryAnalysis,
    TrajectoryTrend,
    Source,
    SourceRequirement,
    UiDiagnosis,
    UiFinding,
)
from app.diagnosis.recommendations import build_recommendations

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
    if section_name == "security" and section.data.get("sysmon", {}).get("status") == "skipped":
        reason = str(section.data.get("sysmon", {}).get("reason") or "").lower()
        return "permission_required" if "access_denied" in reason or "permission" in reason else "unavailable"
    if section.status == "partial":
        return "permission_required" if _permission_limited(section) else "collected"
    if section.status == "ok":
        return "collected"
    return "unavailable"


def _source_requirements(snapshot: TelemetrySnapshot, name: str, section_name: str, status: str) -> list[SourceRequirement]:
    """Expose actionable prerequisites without leaking event-log error text."""
    if status in {"collected", "not_in_scope"}:
        return []
    if name == "sysmon":
        section = snapshot.sections.get(section_name)
        reason = str((section.data.get("sysmon") or {}).get("reason") or "") if section else ""
        if reason == "sysmon_setup_restart_required":
            return [
                SourceRequirement(
                    title="Windows 다시 시작 필요",
                    detail="내장 Sysmon 기능을 활성화했습니다. 재시작 후 다시 진단하면 이벤트 수집을 자동으로 완료합니다.",
                ),
            ]
        if status == "permission_required":
            return [
                SourceRequirement(
                    title="관리자 권한 또는 이벤트 로그 읽기 권한",
                    detail="관리자 권한으로 Local Agent를 실행한 뒤 Sysmon Operational 로그 접근 권한을 확인하세요.",
                ),
            ]
        return [
            SourceRequirement(
                title="Sysmon 설치 및 Operational 로그 활성화",
                detail="Microsoft Sysinternals Sysmon을 설치하고 Microsoft-Windows-Sysmon/Operational 채널을 활성화하세요.",
            ),
            SourceRequirement(
                title="관리자 권한으로 재검사",
                detail="설치 또는 구성 변경 후에는 관리자 Local Agent로 다시 스캔해야 보안 이벤트를 검증할 수 있습니다.",
            ),
        ]
    if status == "permission_required":
        return [
            SourceRequirement(
                title="관리자 권한으로 재검사",
                detail="Windows 관리자 권한이 필요한 수집 항목입니다. 관리자 Local Agent로 다시 스캔하세요.",
            ),
        ]
    return [
        SourceRequirement(
            title="수집 환경 확인",
            detail="해당 Windows 기능 또는 장치가 사용 가능한지 확인한 뒤 다시 스캔하세요.",
        ),
    ]


def _sources(snapshot: TelemetrySnapshot) -> list[Source]:
    collected_at = snapshot.collected_at.isoformat()
    return [
        Source(
            name=name,
            status=(status := _source_status(snapshot, section_name)),
            collectedAt=collected_at if status == "collected" else None,
            requirements=_source_requirements(snapshot, name, section_name, status),
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


def _category(snapshot: TelemetrySnapshot, findings: list[Finding], axis: str, diagnosis_status: str) -> CategorySummary:
    selected = [item for item in findings if item.axis.value == axis]
    highest = max(selected, key=lambda item: _SEVERITY_ORDER[item.severity]).severity if selected else Severity.INFO
    labels = {"hardware": "하드웨어", "software": "소프트웨어", "security": "보안"}
    if selected:
        summary = "{0} 점검 항목 {1}건".format(labels[axis], len(selected))
    elif axis == "security":
        security = snapshot.section("security")
        sysmon = security.data.get("sysmon") if security and isinstance(security.data.get("sysmon"), dict) else {}
        if sysmon.get("status") == "ok":
            summary = "보안 이벤트를 수집했지만 확정된 이상은 없습니다"
        elif security and security.status in {"partial", "failed"}:
            summary = "보안 이벤트를 모두 수집하지 못해 판단을 보류함"
        else:
            summary = "보안 이벤트 수집 범위 밖"
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


def _root_cause_candidates(snapshot: TelemetrySnapshot) -> list[RootCauseCandidate]:
    """Translate the local M6 output without exposing process keys or raw logs."""
    section = snapshot.section("correlation")
    if section is None:
        return []
    candidates = section.data.get("candidates")
    if not isinstance(candidates, list):
        return []

    labels = {
        "background_load": {
            "title": "백그라운드 작업 부하 후보",
            "summary": "높은 CPU 사용량과 동일 프로세스의 생성·통신 활동이 같은 시간대에 관측됐습니다.",
            "action": ActionType.FIX,
        },
        "hardware_instability": {
            "title": "하드웨어 불안정 후보",
            "summary": "WHEA 하드웨어 오류와 디스크 오류가 같은 시간대에 관측됐습니다.",
            "action": ActionType.FIX,
        },
    }
    output: list[RootCauseCandidate] = []
    for raw in candidates[:3]:
        if not isinstance(raw, dict) or raw.get("id") not in labels:
            continue
        confidence = _number(raw.get("confidence"))
        rank = raw.get("rank")
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
        if confidence is None or not isinstance(rank, int) or not 1 <= rank <= 3:
            continue
        if raw["id"] == "background_load":
            ids = evidence.get("event_ids") if isinstance(evidence.get("event_ids"), list) else []
            event_labels = {1: "프로세스 생성", 3: "네트워크 연결", 22: "DNS 조회"}
            observed = [event_labels[item] for item in ids if item in event_labels]
            proof = ["CPU 사용률 {0}%".format(evidence.get("cpu_percent", "-"))]
            if observed:
                proof.append("동일 프로세스의 " + "·".join(observed) + " 활동")
        else:
            proof = ["WHEA 오류 {0}건".format(evidence.get("whea_count", "-")),
                     "디스크 오류 {0}건".format(evidence.get("disk_count", "-"))]
        window = evidence.get("window_seconds")
        if isinstance(window, int) and window > 0:
            proof.append("{0}초 시간 창에서 상관됨".format(window))
        label = labels[raw["id"]]
        output.append(RootCauseCandidate(
            id=raw["id"], rank=rank, confidence=confidence, action=label["action"],
            title=label["title"], summary=label["summary"], evidence=proof,
            limitation="시간상 연관성 기반 후보이며, 원인이나 보안 위협을 확정하지 않습니다.",
        ))
    return sorted(output, key=lambda item: item.rank)


def _anomaly_analysis(snapshot: TelemetrySnapshot) -> AnomalyAnalysis:
    """Expose local M7 signals as context, never as a diagnosis or risk score."""
    section = snapshot.section("anomaly")
    limitation = "통계적 상태 변화 신호이며, 고장·보안 위협·교체 필요를 확정하지 않습니다."
    if section is None:
        return AnomalyAnalysis(status="unavailable", limitation="이전 실제 측정이 없어 상태 변화 분석을 수행하지 못했습니다.")
    data = section.data
    raw_signals = data.get("signals") if isinstance(data.get("signals"), list) else []
    labels = {
        "performance.cpu.usage_percent": "CPU 사용률",
        "performance.memory.committed_percent": "메모리 사용률",
        "performance.disk.queue_length": "디스크 대기열",
        "storage.free_percent": "시스템 드라이브 여유 공간",
        "reliability.whea_count": "WHEA 하드웨어 오류 수",
    }
    signals: list[AnomalySignal] = []
    for raw in raw_signals[:5]:
        if not isinstance(raw, dict):
            continue
        metric = raw.get("metric")
        value, baseline, z_score = _number(raw.get("value")), _number(raw.get("baseline_mean")), _number(raw.get("z_score"))
        samples = raw.get("samples")
        if not isinstance(metric, str) or value is None or baseline is None or z_score is None or not isinstance(samples, int) or samples < 3:
            continue
        disk_label = "저장장치 상태" if metric.startswith("disk.") else None
        label = labels.get(metric) or disk_label
        if label is None:
            continue
        signals.append(AnomalySignal(
            metric=metric, label=label,
            direction="above_baseline" if z_score > 0 else "below_baseline",
            zScore=z_score, value=value, baselineMean=baseline, samples=samples,
        ))
    evaluated = data.get("evaluated_metrics")
    evaluated = evaluated if isinstance(evaluated, int) and evaluated >= 0 else 0
    required = data.get("required_baseline_samples")
    required = required if isinstance(required, int) and required >= 3 else 3
    if signals:
        status = "signal_detected"
    elif section.status == "ok":
        status = "no_signal"
    else:
        status = "insufficient"
    return AnomalyAnalysis(
        status=status, method="z_score" if data.get("method") == "z_score" else None,
        evaluatedMetrics=evaluated, requiredBaselineSamples=required,
        signals=signals, limitation=limitation,
    )


def _trajectory_analysis(snapshot: TelemetrySnapshot) -> TrajectoryAnalysis:
    """Translate local M8 regression output without promising a physical failure date."""
    section = snapshot.section("trajectory")
    limitation = "선형 추세의 탐색용 근사이며, 실제 고장 시점이나 교체 필요를 예측하지 않습니다."
    if section is None:
        return TrajectoryAnalysis(status="unavailable", limitation="최소 3회, 1일 이상의 실제 측정 이력이 필요합니다.")
    data = section.data
    raw_trends = data.get("trends") if isinstance(data.get("trends"), list) else []
    labels = {
        "storage.free_percent": "시스템 드라이브 여유 공간",
    }
    trends: list[TrajectoryTrend] = []
    for raw in raw_trends[:5]:
        if not isinstance(raw, dict):
            continue
        metric = raw.get("metric")
        slope = _number(raw.get("slope_per_day"))
        samples = raw.get("samples")
        if not isinstance(metric, str) or slope is None or not isinstance(samples, int) or samples < 3:
            continue
        if metric == "storage.free_percent":
            label, adverse = labels[metric], slope < -0.01
            improving = slope > 0.01
        elif metric.startswith("disk.") and metric.endswith("wear_percent"):
            label, adverse = "저장장치 수명 소모", slope > 0.01
            improving = slope < -0.01
        elif metric.startswith("disk.") and metric.endswith("reallocated_sectors"):
            label, adverse = "저장장치 재할당 섹터", slope > 0.01
            improving = slope < -0.01
        else:
            continue
        direction = "worsening" if adverse else "improving" if improving else "stable"
        threshold = _number(raw.get("threshold"))
        threshold_at = raw.get("threshold_at") if isinstance(raw.get("threshold_at"), str) else None
        raw_range = raw.get("threshold_at_interval_approx")
        threshold_range = raw_range if isinstance(raw_range, list) and len(raw_range) == 2 and all(isinstance(item, str) for item in raw_range) else None
        trends.append(TrajectoryTrend(
            metric=metric, label=label, direction=direction, samples=samples,
            slopePerDay=slope, threshold=threshold, thresholdAt=threshold_at,
            thresholdRange=threshold_range,
        ))
    required = data.get("required_samples")
    required = required if isinstance(required, int) and required >= 3 else 3
    span = data.get("minimum_span_days")
    span = span if isinstance(span, int) and span >= 1 else 1
    return TrajectoryAnalysis(
        status="ready" if trends else "insufficient",
        method="linear_regression" if data.get("method") == "linear_regression" else None,
        requiredSamples=required, minimumSpanDays=span, trends=trends, limitation=limitation,
    )


def to_ui_diagnosis(
    snapshot: TelemetrySnapshot,
    result: DiagnosisResult,
    ai: dict[str, Any],
    recommendations: list[Recommendation] | None = None,
) -> UiDiagnosis:
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
            hardware=_category(snapshot, findings, "hardware", status),
            software=_category(snapshot, findings, "software", status),
            security=_category(snapshot, findings, "security", status),
        ),
        resources=_resources(snapshot, findings),
        findings=_findings(findings),
        inventory=_inventory(snapshot, findings),
        sources=_sources(snapshot),
        rootCauseCandidates=_root_cause_candidates(snapshot),
        anomalyAnalysis=_anomaly_analysis(snapshot),
        trajectoryAnalysis=_trajectory_analysis(snapshot),
        ai=AiDiagnosis.model_validate(ai),
        decision=Decision(
            action=result.decision.action,
            reason=result.decision.reason,
            drivenBy=result.decision.driven_by,
        ),
        recommendations=(
            recommendations if recommendations is not None else build_recommendations(snapshot, result)
        ),
    )
