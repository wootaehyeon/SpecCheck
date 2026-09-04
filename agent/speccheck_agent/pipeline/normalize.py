"""정규화 (M3).

원시 telemetry를 진단/견적 계층이 바로 쓸 수 있는 형태로 줄인다.
특히 ``to_spec_profile`` 은 Agent 스냅샷을 기존 SpecCheck 견적 시스템
(호환성/가격/벤치마크)의 입력 형태로 바꾸는 다리 역할을 한다 (Phase 5).

**키 집합은 수집 결과와 무관하게 항상 같다.** 섹션이 없으면 키가 사라지는
것이 아니라 값이 ``None`` 이 된다. 소비자(Backend, 견적 로직)가 Actual/Estimated
경로를 구분하거나 키 존재 여부를 방어할 필요가 없게 하기 위해서다.
"""

from __future__ import annotations

from typing import Any


def _section_data(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    section = (snapshot.get("sections") or {}).get(name) or {}
    if section.get("status") not in ("ok", "partial"):
        return {}
    return section.get("data") or {}


def to_spec_profile(snapshot: dict[str, Any]) -> dict[str, Any]:
    """스냅샷에서 부품 사양 프로필을 추출한다.

    반환 형태는 Estimated Scan(사용자 직접 입력)과 동일하다. 덕분에
    호환성/가격/벤치마크 로직은 Actual/Estimated를 구분하지 않고 동작한다.
    """
    hardware = _section_data(snapshot, "hardware")
    storage_health = _section_data(snapshot, "storage_health")

    cpus = hardware.get("cpu") or []
    gpus = hardware.get("gpu") or []
    memory = hardware.get("memory") or {}
    storage = hardware.get("storage") or []
    board = hardware.get("motherboard") or {}

    primary_cpu = cpus[0] if cpus else {}
    # 내장 그래픽과 외장 그래픽이 함께 잡히면 외장을 우선한다.
    primary_gpu = _pick_discrete_gpu(gpus)

    return {
        "source": snapshot.get("scan_mode", "actual"),
        "cpu": {
            "name": primary_cpu.get("name"),
            "cores": primary_cpu.get("cores"),
            "threads": primary_cpu.get("threads"),
            "max_clock_mhz": primary_cpu.get("max_clock_mhz"),
        },
        "gpu": {
            "name": primary_gpu.get("name"),
            "vram_gb": primary_gpu.get("adapter_ram_gb"),
            "driver_date": primary_gpu.get("driver_date"),
        },
        "memory": {
            "total_gb": memory.get("total_gb"),
            "module_count": memory.get("module_count"),
            "slot_count": memory.get("slot_count"),
            "empty_slot_count": memory.get("empty_slot_count"),
            "configured_speed_mhz": _first(memory.get("modules"), "configured_speed_mhz"),
        },
        # 인벤토리(무엇이 달렸는가)에 수명(얼마나 닳았는가)을 합쳐 하나로 낸다.
        # Estimated Scan에서는 수명 키가 전부 None으로 채워진다.
        "storage": [
            _merge_disk(disk, storage_health.get("disks") or [])
            for disk in storage
        ],
        "motherboard": {
            "manufacturer": board.get("manufacturer"),
            "product": board.get("product"),
        },
        "health": to_health_profile(snapshot),
    }


def to_health_profile(snapshot: dict[str, Any]) -> dict[str, Any]:
    """M2 telemetry(저장장치 수명 / 이벤트 / 성능)를 한 겹으로 요약한다.

    규칙 엔진은 원본 섹션을 직접 보지만, 견적·UI 계층은 이 요약만 있으면 된다.
    """
    storage_health = _section_data(snapshot, "storage_health")
    reliability = _section_data(snapshot, "reliability")
    performance = _section_data(snapshot, "performance")

    system_volume = _system_volume(storage_health)
    cpu = performance.get("cpu") or {}
    memory = performance.get("memory") or {}
    totals = reliability.get("totals") or {}

    return {
        "system_volume": {
            "drive": system_volume.get("drive"),
            "size_gb": system_volume.get("size_gb"),
            "free_gb": system_volume.get("free_gb"),
            "free_percent": system_volume.get("free_percent"),
        },
        "worst_disk": _worst_disk(storage_health.get("disks") or []),
        "events": {
            "window_days": reliability.get("window_days"),
            "whea_corrected": totals.get("whea_corrected"),
            "whea_fatal": totals.get("whea_fatal"),
            "unexpected_shutdown": totals.get("unexpected_shutdown"),
            "bugcheck": totals.get("bugcheck"),
            "disk_error": totals.get("disk_error"),
        },
        "load": {
            "cpu_avg_percent": (cpu.get("usage_percent") or {}).get("avg"),
            "cpu_max_percent": (cpu.get("usage_percent") or {}).get("max"),
            "memory_available_mb": (memory.get("available_mb") or {}).get("avg"),
            "memory_committed_percent": (memory.get("committed_percent") or {}).get("avg"),
            "clock_ratio": (cpu.get("clock") or {}).get("ratio"),
            "power_plan": (performance.get("power_plan") or {}).get("scheme"),
            "top_process": _top_process_name(performance.get("top_processes") or []),
        },
    }


def section_summaries(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """섹션별 수집 상태 요약. CLI와 UI가 "무엇을 봤는가"를 보여줄 때 쓴다.

    상태가 ``ok`` 가 아닌 섹션도 반드시 남긴다. 못 본 것을 "이상 없음"으로
    보이게 하지 않는 것이 진단 신뢰도의 출발점이다.
    """
    summaries = []
    for name, section in (snapshot.get("sections") or {}).items():
        summaries.append(
            {
                "name": name,
                "status": section.get("status"),
                "milestone": section.get("milestone"),
                "duration_ms": section.get("duration_ms"),
                "error": section.get("error"),
                "headline": _headline(name, section),
            }
        )
    return summaries


# --- 내부 헬퍼 ---------------------------------------------------------------


def _pick_discrete_gpu(gpus: list[dict[str, Any]]) -> dict[str, Any]:
    """외장 GPU 우선. 노트북처럼 내장만 있으면 그것을 쓴다."""
    if not gpus:
        return {}
    for gpu in gpus:
        if not gpu.get("integrated"):
            return gpu
    return gpus[0]


def _first(items: list[dict[str, Any]] | None, key: str) -> Any:
    for item in items or []:
        if item.get(key) is not None:
            return item[key]
    return None


def _normalized_model(value: Any) -> str:
    return " ".join(str(value or "").split()).lower()


def _merge_disk(disk: dict[str, Any], health_disks: list[dict[str, Any]]) -> dict[str, Any]:
    """인벤토리 디스크 한 대에 대응하는 수명 정보를 붙인다.

    두 목록 모두 ``Win32_DiskDrive`` 를 출발점으로 하지만 열거 순서가 같다고
    가정하지 않는다. 모델명과 용량으로 맞춰야 USB 디스크가 끼어들어도 어긋나지 않는다.
    """
    match: dict[str, Any] = {}
    model = _normalized_model(disk.get("model"))
    for candidate in health_disks:
        if _normalized_model(candidate.get("model")) != model:
            continue
        size, candidate_size = disk.get("size_gb"), candidate.get("size_gb")
        if size is not None and candidate_size is not None and abs(size - candidate_size) > 1:
            continue
        match = candidate
        break

    return {
        "model": disk.get("model"),
        "size_gb": disk.get("size_gb"),
        "media_type": disk.get("media_type"),
        "bus_type": disk.get("bus_type"),
        "wear_percent": match.get("wear_percent"),
        "power_on_hours": match.get("power_on_hours"),
        "reallocated_sectors": match.get("reallocated_sectors"),
        "pending_sectors": match.get("pending_sectors"),
        "predict_failure": match.get("predict_failure"),
    }


def _system_volume(storage_health: dict[str, Any]) -> dict[str, Any]:
    for volume in storage_health.get("volumes") or []:
        if volume.get("is_system"):
            return volume
    return {}


def _worst_disk(disks: list[dict[str, Any]]) -> dict[str, Any]:
    """가장 상태가 나쁜 디스크 한 대. 없으면 키만 있는 빈 형태를 낸다."""
    empty = {
        "model": None,
        "wear_percent": None,
        "reallocated_sectors": None,
        "pending_sectors": None,
        "predict_failure": None,
    }
    if not disks:
        return empty

    def score(disk: dict[str, Any]) -> tuple[int, int, int]:
        return (
            1 if disk.get("predict_failure") else 0,
            (disk.get("reallocated_sectors") or 0) + (disk.get("pending_sectors") or 0),
            disk.get("wear_percent") or 0,
        )

    worst = max(disks, key=score)
    return {key: worst.get(key) for key in empty}


def _top_process_name(processes: list[dict[str, Any]]) -> str | None:
    return processes[0].get("name") if processes else None


def _headline(name: str, section: dict[str, Any]) -> str | None:
    """섹션 하나를 사람이 읽는 한 줄로 줄인다."""
    if section.get("status") not in ("ok", "partial"):
        return section.get("error")

    data = section.get("data") or {}
    if name == "hardware":
        cpus = data.get("cpu") or []
        memory = data.get("memory") or {}
        return "{0} / RAM {1}GB / 디스크 {2}대".format(
            (cpus[0].get("name") if cpus else None) or "CPU 미상",
            memory.get("total_gb"),
            len(data.get("storage") or []),
        )
    if name == "storage_health":
        volume = _system_volume(data)
        return "시스템 볼륨 {0} 여유 {1}GB ({2}%) / 디스크 {3}대".format(
            volume.get("drive") or "?",
            volume.get("free_gb"),
            volume.get("free_percent"),
            len(data.get("disks") or []),
        )
    if name == "reliability":
        totals = data.get("totals") or {}
        return "{0}일간 WHEA {1}건 / 비정상 종료 {2}건 / 디스크 오류 {3}건".format(
            data.get("window_days"),
            (totals.get("whea_corrected") or 0) + (totals.get("whea_fatal") or 0),
            totals.get("unexpected_shutdown") or 0,
            totals.get("disk_error") or 0,
        )
    if name == "performance":
        cpu = (data.get("cpu") or {}).get("usage_percent") or {}
        memory = (data.get("memory") or {}).get("available_mb") or {}
        return "CPU 평균 {0}% (최대 {1}%) / 가용 메모리 {2}MB / 전원 {3}".format(
            cpu.get("avg"),
            cpu.get("max"),
            memory.get("avg"),
            (data.get("power_plan") or {}).get("name") or "?",
        )
    return None
