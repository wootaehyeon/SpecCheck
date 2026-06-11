"""
해외(eBay) 중고 시세 기반 견적 최적화 엔진.

두 가지 모드를 제공합니다.
  - "save"    : 같은 부품을 중고가로 대체했을 때의 절감액 계산 (가격 낮추기)
  - "upgrade" : 동일 예산 안에서 더 높은 벤치마크 점수의 부품으로 교체 (성능 향상)

벤치마크 데이터(backend/data/{cpu,gpu}_benchmark.json)는
  { "<부품명>": {"score": int, "price_usd": float, "tdp": int, "category": str}, ... }
형태이며 upgrade 모드의 후보 탐색에 사용합니다.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.services.ebay_api import search_used_price, get_usd_krw_rate

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# 업그레이드 후보는 소비자용 데스크톱 부품으로 한정 (서버/워크스테이션/노트북/임베디드 제외)
_NON_CONSUMER = ("server", "workstation", "mobile", "laptop", "embedded")
# upgrade 모드에서 부품당 최대 중고가 조회 횟수 (eBay 호출 비용 제한)
MAX_UPGRADE_LOOKUPS = 8
# 신품가(MSRP) 대비 이 비율보다 싼 중고 매물은 오매칭(액세서리/박스 등)으로 간주.
# 데이터셋 MSRP가 출시 당시 고가로 기록된 경우가 많아 낮게 잡는다.
MIN_USED_TO_MSRP_RATIO = 0.15


def _is_consumer_desktop(category: Optional[str]) -> bool:
    cat = (category or "").lower()
    if "desktop" not in cat:
        return False
    return not any(x in cat for x in _NON_CONSUMER)


@lru_cache(maxsize=4)
def _load_benchmark(kind: str) -> Dict[str, dict]:
    path = DATA_DIR / f"{kind}_benchmark.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_TOKEN_RE = re.compile(r"[a-z0-9]+")
# 매칭 정확도를 높이기 위해 무시할 일반 단어
# 주의: 'ti'/'super'는 GPU 등급을 구분하는 의미 토큰이므로 불용어에 넣지 않는다.
_STOP_TOKENS = {
    "amd", "intel", "nvidia", "geforce", "radeon", "ryzen", "core",
    "processor", "cpu", "gpu", "graphics", "card", "edition", "series",
    "gddr6", "gb", "the", "with",
}
# 한글 모델명 → 영문 토큰 보정
_KO_ALIASES = {
    "라이젠": "ryzen",
    "지포스": "geforce",
    "라데온": "radeon",
    "인텔": "intel",
}


def _normalize_tokens(name: str) -> List[str]:
    if not name:
        return []
    lower = name.lower()
    for ko, en in _KO_ALIASES.items():
        lower = lower.replace(ko, en)
    return [t for t in _TOKEN_RE.findall(lower) if t not in _STOP_TOKENS]


def _has_model_number(tokens: List[str]) -> List[str]:
    """모델 식별 토큰만 추출 (예: 4070, 5600x, 13900k).

    숫자 3자리 이상을 포함하는 토큰만 인정한다. 'i9', 'i7', '5'(브랜드 등급) 같은
    짧은 토큰을 모델 번호로 오인해 서로 다른 칩이 매칭되는 것을 방지한다.
    """
    return [t for t in tokens if sum(ch.isdigit() for ch in t) >= 3]


def _match_score(query_tokens: List[str], key_tokens: List[str]) -> float:
    if not query_tokens or not key_tokens:
        return 0.0
    qset, kset = set(query_tokens), set(key_tokens)
    shared = qset & kset
    if not shared:
        return 0.0

    score = len(shared) / len(qset)

    # 모델 번호(숫자 토큰)가 일치하면 강하게 가중
    q_models = set(_has_model_number(query_tokens))
    k_models = set(_has_model_number(key_tokens))
    if q_models and q_models & k_models:
        score += 2.0
    elif q_models and not (q_models & k_models):
        # 모델 번호가 명확히 다르면 오답 가능성 높음 → 감점
        score -= 0.5

    # 키에만 있는 잉여 토큰(예: 'ti', 'super')은 약하게 감점해
    # 동점일 때 더 정확한(짧은) 이름을 선호하도록 한다.
    extra = len(kset - qset)
    score -= 0.01 * extra

    return score


def find_benchmark_entry(name: str, kind: str) -> Optional[Tuple[str, dict]]:
    """부품명에 가장 잘 맞는 벤치마크 항목 (정식명, 데이터) 반환."""
    bench = _load_benchmark(kind)
    if not bench:
        return None

    q_tokens = _normalize_tokens(name)
    best_key, best_score = None, 0.0
    for key, data in bench.items():
        s = _match_score(q_tokens, _normalize_tokens(key))
        if s > best_score:
            best_key, best_score = key, s

    # 임계값: 모델 번호 매칭(>=2) 또는 토큰 50% 이상 겹침
    if best_key and best_score >= 1.0:
        return best_key, bench[best_key]
    return None


# 부품 key → 벤치마크 종류 매핑
_KIND_BY_KEY = {"cpu": "cpu", "gpu": "gpu"}


def _kind_for_part(part: dict) -> Optional[str]:
    key = (part.get("key") or "").lower()
    if key in _KIND_BY_KEY:
        return _KIND_BY_KEY[key]
    category = (part.get("category") or "").upper()
    if category == "CPU":
        return "cpu"
    if category == "GPU":
        return "gpu"
    return None


# ---------------------------------------------------------------------------
# save 모드: 같은 부품 중고가 대체
# ---------------------------------------------------------------------------
def _evaluate_save(part: dict) -> dict:
    name = part.get("name") or ""
    user_price = int(part.get("userPrice") or 0)
    used = search_used_price(name)

    base = {
        "key": part.get("key"),
        "category": part.get("category"),
        "name": name,
        "userPrice": user_price,
        "usedFound": bool(used.get("found")),
        "source": used.get("source"),
    }

    if not used.get("found"):
        return {**base, "recommend": False, "reason": "해외 중고 시세를 찾지 못했습니다.", "savings": 0}

    # 의사결정은 단일 쓰레기 매물에 강건한 robust_low 사용 (없으면 절대 최저가)
    used_low = used.get("robust_low_krw") or used["lowest_price_krw"]
    used_avg = used["average_price_krw"]
    savings = user_price - used_low if user_price > 0 else 0

    recommend = user_price > 0 and used_low < user_price
    if recommend:
        reason = (
            f"동일 부품을 해외 중고로 약 {used_low:,}원에 구할 수 있어 "
            f"입력가 대비 {savings:,}원 절감됩니다."
        )
    elif user_price > 0:
        reason = "입력 가격이 이미 해외 중고 최저가와 비슷하거나 더 낮습니다."
    else:
        reason = f"해외 중고 최저가는 약 {used_low:,}원입니다."

    return {
        **base,
        "usedLowestKRW": used_low,
        "usedAverageKRW": used_avg,
        "usedLowestUSD": used.get("lowest_price_usd"),
        "currency": used.get("currency"),
        "usdKrwRate": used["usd_krw_rate"],
        "listingCount": used["listing_count"],
        "sampleLink": used.get("sample_link"),
        "recommend": recommend,
        "reason": reason,
        "savings": max(0, savings) if recommend else 0,
    }


# ---------------------------------------------------------------------------
# upgrade 모드: 동일 예산 내 성능 향상
# ---------------------------------------------------------------------------
def _evaluate_upgrade(part: dict, budget_tolerance: float = 0.05) -> dict:
    name = part.get("name") or ""
    user_price = int(part.get("userPrice") or 0)
    kind = _kind_for_part(part)

    base = {
        "key": part.get("key"),
        "category": part.get("category"),
        "name": name,
        "userPrice": user_price,
    }

    if not kind:
        return {**base, "upgradeable": False, "reason": "성능 벤치마크가 없는 부품(CPU/GPU만 지원)."}

    current = find_benchmark_entry(name, kind)
    if not current:
        return {**base, "upgradeable": False, "reason": "현재 부품의 벤치마크 정보를 찾지 못했습니다."}

    current_key, current_data = current
    current_score = current_data.get("score", 0)

    # 예산: 입력가 + 약간의 허용치 (동 가격대)
    if user_price <= 0:
        return {**base, "upgradeable": False, "reason": "입력 가격이 없어 동일 예산 비교가 불가합니다.",
                "currentBenchmark": current_key, "currentScore": current_score}

    rate = get_usd_krw_rate()
    budget_krw = int(user_price * (1 + budget_tolerance))

    bench = _load_benchmark(kind)
    # 현재보다 점수가 높은 소비자용 데스크톱 후보를, 점수 높은 순으로 정렬
    candidates = [
        (key, data) for key, data in bench.items()
        if data.get("score", 0) > current_score
        and _is_consumer_desktop(data.get("category"))
        # 신품가 정보가 있어야 가격 정합성 검증이 가능 (오매칭 후보 차단)
        and data.get("price_usd", 0) > 0
        # 중고가는 보통 신품가의 50~70% 수준. 신품가(KRW 환산)가 예산의 2.5배를
        # 넘으면 중고가도 예산에 들 가능성이 낮으므로 사전 제거해 조회를 집중.
        # (데이터셋 MSRP가 고가로 기록된 경우를 감안해 넉넉히 잡음)
        and data.get("price_usd", 0) * rate <= budget_krw * 2.5
    ]
    candidates.sort(key=lambda kv: kv[1].get("score", 0), reverse=True)

    best = None
    lookups = 0
    for key, data in candidates:
        if lookups >= MAX_UPGRADE_LOOKUPS:
            break
        used = search_used_price(key)
        lookups += 1
        if not used.get("found"):
            continue
        used_low = used.get("robust_low_krw") or used["lowest_price_krw"]
        # 가격 정합성: 신품가(MSRP) 대비 지나치게 싼 매물은 오매칭으로 보고 건너뜀
        msrp_krw = data["price_usd"] * rate
        if used_low < msrp_krw * MIN_USED_TO_MSRP_RATIO:
            continue
        if used_low <= budget_krw:
            # 점수 내림차순이므로 예산에 맞는 첫 후보가 곧 예산 내 최고 성능
            best = {
                "benchmark": key,
                "score": data.get("score", 0),
                "usedLowestKRW": used_low,
                "usedLowestUSD": used.get("lowest_price_usd"),
                "sampleLink": used.get("sample_link"),
                "listingCount": used["listing_count"],
            }
            break

    if not best:
        return {
            **base,
            "currentBenchmark": current_key,
            "currentScore": current_score,
            "upgradeable": False,
            "reason": "동일 예산 내에서 더 높은 성능의 중고 부품을 찾지 못했습니다.",
        }

    gain = best["score"] - current_score
    gain_pct = round(gain / current_score * 100, 1) if current_score else 0.0
    return {
        **base,
        "currentBenchmark": current_key,
        "currentScore": current_score,
        "upgradeable": True,
        "recommendedPart": best["benchmark"],
        "recommendedScore": best["score"],
        "recommendedUsedKRW": best["usedLowestKRW"],
        "recommendedUsedUSD": best["usedLowestUSD"],
        "scoreGain": gain,
        "scoreGainPct": gain_pct,
        "sampleLink": best["sampleLink"],
        "listingCount": best["listingCount"],
        "reason": (
            f"동일 예산(약 {user_price:,}원)으로 '{best['benchmark']}'를 해외 중고 약 "
            f"{best['usedLowestKRW']:,}원에 구하면 벤치마크 점수가 "
            f"{current_score:,} → {best['score']:,} (+{gain_pct}%) 향상됩니다."
        ),
    }


# ---------------------------------------------------------------------------
# 공개 진입점
# ---------------------------------------------------------------------------
def optimize_estimate(parts: List[dict], mode: str = "save", purpose: str = "게임") -> dict:
    """
    parts: [{key, category, name, userPrice}, ...]
    mode : "save" | "upgrade" | "both"
    """
    mode = (mode or "save").lower()
    rate = get_usd_krw_rate()
    input_total = sum(int(p.get("userPrice") or 0) for p in parts)

    result: Dict = {
        "mode": mode,
        "purpose": purpose,
        "usdKrwRate": round(rate, 2),
        "inputTotal": input_total,
    }

    if mode in ("save", "both"):
        save_items = [_evaluate_save(p) for p in parts]
        total_savings = sum(i.get("savings", 0) for i in save_items if i.get("recommend"))
        # 절감 적용 후 합계: 추천 항목은 중고 최저가로, 그 외는 입력가 유지
        optimized_total = sum(
            (i["usedLowestKRW"] if i.get("recommend") else i["userPrice"])
            for i in save_items
        )
        result["save"] = {
            "items": save_items,
            "totalSavings": total_savings,
            "optimizedTotal": optimized_total,
            "inputTotal": input_total,
            "savingsRate": round(total_savings / input_total * 100, 1) if input_total else 0.0,
        }

    if mode in ("upgrade", "both"):
        upgrade_items = [_evaluate_upgrade(p) for p in parts]
        total_score_gain = sum(i.get("scoreGain", 0) for i in upgrade_items if i.get("upgradeable"))
        result["upgrade"] = {
            "items": upgrade_items,
            "totalScoreGain": total_score_gain,
            "upgradeableCount": sum(1 for i in upgrade_items if i.get("upgradeable")),
        }

    return result


if __name__ == "__main__":
    sample = [
        {"key": "cpu", "category": "CPU", "name": "AMD Ryzen 5 5600X", "userPrice": 200000},
        {"key": "gpu", "category": "GPU", "name": "RTX 3060", "userPrice": 350000},
    ]
    print(json.dumps(optimize_estimate(sample, mode="both"), indent=2, ensure_ascii=False))
