import json
from pathlib import Path
from math import ceil

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load(filename: str) -> dict:
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_component(benchmark: dict, query: str):
    if not query:
        return None, None
    q = query.lower().strip()
    for name, data in benchmark.items():
        if name.lower() == q:
            return name, data
    for name, data in benchmark.items():
        if q in name.lower() or name.lower() in q:
            return name, data
    return None, None


def check_compatibility(build: dict) -> dict:
    """호환성 검사: CPU-메인보드 소켓(간단 매칭), RAM 세대, PSU 용량, 저장장치 인터페이스

    Returns: { issues: [..], estimated_required_watt: int, recommended_psu_watt: int }
    """
    cpu_db = _load("cpu_benchmark.json")
    gpu_db = _load("gpu_benchmark.json")

    cpu_name, cpu_data = _find_component(cpu_db, build.get("cpu", ""))
    gpu_name, gpu_data = _find_component(gpu_db, build.get("gpu", ""))

    issues = []

    # RAM generation
    ram = (build.get("ram") or "").lower()
    mobo = (build.get("motherboard") or "").lower()
    if "ddr5" in ram and "ddr4" in mobo:
        issues.append({"type": "error", "component": "RAM / 메인보드",
                       "message": "DDR5 RAM과 DDR4 지원 메인보드는 호환되지 않습니다."})
    elif "ddr4" in ram and "ddr5" in mobo:
        issues.append({"type": "error", "component": "RAM / 메인보드",
                       "message": "DDR4 RAM과 DDR5 지원 메인보드는 호환되지 않습니다."})

    # CPU/메인보드 소켓 간단 판별 (키워드 기반)
    is_intel = any(k in (build.get("cpu") or "").lower() for k in ["intel", "i3", "i5", "i7", "i9"])
    is_amd = any(k in (build.get("cpu") or "").lower() for k in ["ryzen", "amd", "r5", "r7", "r9"])
    amd_socket_keywords = ["am4", "am5", "b550", "x570", "b650", "x670"]
    intel_socket_keywords = ["lga1700", "lga1200", "z790", "z690", "b760", "h770"]
    if is_intel and any(k in mobo for k in amd_socket_keywords):
        issues.append({"type": "error", "component": "CPU / 메인보드",
                       "message": "Intel CPU는 AMD 소켓 메인보드와 호환되지 않습니다."})
    if is_amd and any(k in mobo for k in intel_socket_keywords):
        issues.append({"type": "error", "component": "CPU / 메인보드",
                       "message": "AMD CPU는 Intel 소켓 메인보드와 호환되지 않습니다."})

    # PSU wattage estimate
    cpu_tdp = int(cpu_data.get("tdp", 0)) if cpu_data else 65
    gpu_tdp = int(gpu_data.get("tdp", 0)) if gpu_data else 0
    # baseline for other components
    others = 100
    estimated_required = cpu_tdp + gpu_tdp + others
    # recommend 25% headroom
    recommended = int(ceil(estimated_required * 1.25 / 10.0)) * 10

    psu_watt = build.get("psu_watt") or 0
    if psu_watt and psu_watt < recommended:
        issues.append({"type": "error", "component": "PSU",
                       "message": f"권장 PSU: {recommended}W 이상입니다. 입력된 PSU: {psu_watt}W"})

    # Storage interface checks
    storage_list = build.get("storage") or []
    supports_m2 = any(k in mobo for k in ["m.2", "m2", "nvme"]) or "m2" in mobo
    has_nvme = any((s.get("type") or "").lower() in ["nvme", "m.2", "m2"] for s in storage_list)
    if has_nvme and not supports_m2:
        issues.append({"type": "warning", "component": "Storage / 메인보드",
                       "message": "메인보드에 M.2 슬롯이 명시되어 있지 않습니다. NVMe 저장장치 장착 여부를 확인하세요."})

    if not issues:
        issues.append({"type": "ok", "component": "전체 호환성",
                       "message": "주요 호환성 이슈가 발견되지 않았습니다. ✅"})

    return {
        "issues": issues,
        "estimated_required_watt": int(estimated_required),
        "recommended_psu_watt": int(recommended),
    }
