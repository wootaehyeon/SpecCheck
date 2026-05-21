from app.logic import evaluator
from app.logic.compatibility import check_compatibility
from app.services.price_manager import get_price


def compute_risk(build: dict) -> dict:
    """Compute a purchase risk score (0-100). Higher = more risky."""
    eval_res = evaluator.evaluate_build(build)

    # price-performance factor
    cpu_price = eval_res.get("cpu_price_krw") or 0
    gpu_price = eval_res.get("gpu_price_krw") or 0
    total_price = 0
    for p in [cpu_price, gpu_price]:
        try:
            if p:
                total_price += int(p)
        except Exception:
            pass

    perf = eval_res.get("overall_score", 50)
    # normalize price-performance: higher perf and lower price -> lower risk
    price_factor = perf / (total_price / 1000 + 1)
    price_perf_score = max(0.0, min(100.0, 100.0 - price_factor))

    # compatibility penalty
    comp = check_compatibility(build)
    comp_issues = comp.get("issues", [])
    comp_penalty = 0.0
    for it in comp_issues:
        if it.get("type") == "error":
            comp_penalty += 30.0
        elif it.get("type") == "warning":
            comp_penalty += 10.0
    comp_penalty = min(comp_penalty, 80.0)

    # storage penalty (if no storage provided)
    storage = build.get("storage") or []
    storage_penalty = 0.0
    if len(storage) == 0:
        storage_penalty = 10.0

    # use-case mismatch: basic heuristic
    use_case = (build.get("use_case") or "").lower()
    use_case_penalty = 0.0
    if use_case:
        if use_case == "gaming" and eval_res.get("gpu_score", 0) < 5000:
            use_case_penalty = 20.0
        if use_case == "workstation" and eval_res.get("cpu_score", 0) < 15000:
            use_case_penalty = 15.0

    # aggregate
    raw_risk = price_perf_score + comp_penalty + storage_penalty + use_case_penalty
    risk_score = int(max(0, min(100, raw_risk)))

    breakdown = {
        "price_performance_factor": round(price_perf_score, 2),
        "compatibility_penalty": round(comp_penalty, 2),
        "storage_penalty": round(storage_penalty, 2),
        "use_case_mismatch_penalty": round(use_case_penalty, 2),
    }

    return {
        "risk_score": risk_score,
        "breakdown": breakdown,
        "compatibility": comp,
        "evaluation": eval_res,
    }
