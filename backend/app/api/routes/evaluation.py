"""견적 평가 라우터.

CPU/GPU 벤치마크 점수, 부품 간 호환성, 구매 위험도(risk score)를 한 번에 계산한다.
계산 로직은 ``app.logic.risk_score.compute_risk`` 에 있고 여기서는 응답 모델로만 옮긴다.
"""

from fastapi import APIRouter

from app.logic.risk_score import compute_risk
from app.schemas.evaluation import BuildRequest, EvaluationResult

router = APIRouter()


@router.post("/evaluate-build", response_model=EvaluationResult)
def evaluate_build(request: BuildRequest):
    """CPU/GPU 성능 평가, 호환성 검사, 구매 위험도 점수를 계산해 반환합니다."""
    risk = compute_risk(request.model_dump())

    eval_data = risk.get("evaluation", {})
    comp = risk.get("compatibility", {})

    return EvaluationResult(
        cpu_matched=eval_data.get("cpu_matched"),
        cpu_score=eval_data.get("cpu_score", 0),
        gpu_matched=eval_data.get("gpu_matched"),
        gpu_score=eval_data.get("gpu_score", 0),
        overall_score=eval_data.get("overall_score", 0),
        tier=eval_data.get("tier", ""),
        compatibility={
            "issues": comp.get("issues", []),
            "estimated_required_watt": comp.get("estimated_required_watt", 0),
            "recommended_psu_watt": comp.get("recommended_psu_watt", 0),
        },
        risk_score=risk.get("risk_score", 0),
        risk_breakdown=risk.get("breakdown", {}),
    )
