"""정규화 (M3).

원시 telemetry를 진단/견적 계층이 바로 쓸 수 있는 형태로 줄인다.
특히 ``to_spec_profile`` 은 Agent 스냅샷을 기존 SpecCheck 견적 시스템
(호환성/가격/벤치마크)의 입력 형태로 바꾸는 다리 역할을 한다 (Phase 5).
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
            "configured_speed_mhz": _first(memory.get("modules"), "configured_speed_mhz"),
        },
        "storage": [
            {
                "model": disk.get("model"),
                "size_gb": disk.get("size_gb"),
                "media_type": disk.get("media_type"),
                "bus_type": disk.get("bus_type"),
            }
            for disk in storage
        ],
        "motherboard": {
            "manufacturer": board.get("manufacturer"),
            "product": board.get("product"),
        },
    }


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
