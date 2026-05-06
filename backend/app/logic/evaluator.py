import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _load(filename: str) -> dict:
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_score(benchmark: dict, query: str) -> tuple:
    """부품명으로 벤치마크 점수 검색 (부분 일치)"""
    q = query.lower().strip()
    # 완전 일치
    for name, score in benchmark.items():
        if name.lower() == q:
            return name, score
    # 부분 일치
    for name, score in benchmark.items():
        if q in name.lower() or name.lower() in q:
            return name, score
    # 키워드 다수 일치
    keywords = [k for k in q.split() if len(k) > 2]
    best, best_cnt = None, 0
    for name, score in benchmark.items():
        cnt = sum(1 for k in keywords if k in name.lower())
        if cnt > best_cnt:
            best_cnt = cnt
            best = (name, score)
    if best and best_cnt > 0:
        return best
    return None, 0


def evaluate_build(build: dict) -> dict:
    cpu_db = _load("cpu_benchmark.json")
    gpu_db = _load("gpu_benchmark.json")

    cpu_name, cpu_score = _find_score(cpu_db, build.get("cpu", ""))
    gpu_name, gpu_score = _find_score(gpu_db, build.get("gpu", ""))

    max_cpu = max(cpu_db.values())
    max_gpu = max(gpu_db.values())

    cpu_norm = (cpu_score / max_cpu * 100) if cpu_score else 0
    gpu_norm = (gpu_score / max_gpu * 100) if gpu_score else 0

    # 병목 계산
    bottleneck_pct = 0.0
    bottleneck_component = "없음"
    if cpu_norm > 0 and gpu_norm > 0:
        diff = abs(cpu_norm - gpu_norm)
        bottleneck_pct = round(min(diff * 1.5, 100), 1)
        if cpu_norm < gpu_norm - 10:
            bottleneck_component = "CPU"
        elif gpu_norm < cpu_norm - 10:
            bottleneck_component = "GPU"

    # 종합 점수
    if cpu_norm > 0 and gpu_norm > 0:
        balance_bonus = max(0, 20 - bottleneck_pct)
        overall = int(cpu_norm * 0.4 + gpu_norm * 0.4 + balance_bonus * 0.2)
    elif cpu_norm > 0:
        overall = int(cpu_norm * 0.5)
    elif gpu_norm > 0:
        overall = int(gpu_norm * 0.5)
    else:
        overall = 50

    overall = min(overall, 100)

    return {
        "cpu_matched": cpu_name,
        "cpu_score": cpu_score,
        "gpu_matched": gpu_name,
        "gpu_score": gpu_score,
        "cpu_norm": round(cpu_norm, 1),
        "gpu_norm": round(gpu_norm, 1),
        "overall_score": overall,
        "bottleneck_percentage": bottleneck_pct,
        "bottleneck_component": bottleneck_component,
        "tier": _tier(overall),
        "compatibility": _check_compatibility(build),
    }


def _tier(score: int) -> str:
    if score >= 85: return "S"
    if score >= 70: return "A"
    if score >= 55: return "B"
    if score >= 40: return "C"
    return "D"


def _check_compatibility(build: dict) -> list:
    issues = []
    cpu = build.get("cpu", "").lower()
    mobo = build.get("motherboard", "").lower()
    ram = build.get("ram", "").lower()

    # RAM 세대 불일치
    if "ddr5" in ram and "ddr4" in mobo:
        issues.append({"type": "error", "component": "RAM / 메인보드",
                        "message": "DDR5 RAM과 DDR4 지원 메인보드는 호환되지 않습니다."})
    elif "ddr4" in ram and "ddr5" in mobo:
        issues.append({"type": "error", "component": "RAM / 메인보드",
                        "message": "DDR4 RAM과 DDR5 지원 메인보드는 호환되지 않습니다."})

    # CPU-소켓 불일치
    is_intel = any(k in cpu for k in ["i3", "i5", "i7", "i9", "intel"])
    is_amd = any(k in cpu for k in ["ryzen", "r5", "r7", "r9", "amd"])
    amd_socket = any(k in mobo for k in ["am4", "am5", "b550", "x570", "b650", "x670"])
    intel_socket = any(k in mobo for k in ["z790", "z690", "b760", "h770", "lga1700", "lga1200"])

    if is_intel and amd_socket:
        issues.append({"type": "error", "component": "CPU / 메인보드",
                        "message": "Intel CPU는 AMD 소켓(AM4/AM5) 메인보드와 호환되지 않습니다."})
    if is_amd and intel_socket:
        issues.append({"type": "error", "component": "CPU / 메인보드",
                        "message": "AMD CPU는 Intel 소켓(LGA1700) 메인보드와 호환되지 않습니다."})

    if not issues:
        issues.append({"type": "ok", "component": "전체 호환성",
                        "message": "주요 호환성 이슈가 발견되지 않았습니다. ✅"})
    return issues
