"""Diagnosis API - 진단 및 Root Cause (M4-M5).

두 가지 경로를 지원한다.

- ``POST /diagnosis/analyze`` : 스냅샷을 그 자리에서 진단 (저장 없이)
- ``POST /diagnosis/{snapshot_id}`` : 이미 업로드된 스냅샷을 진단

두 번째 경로가 있는 이유: 규칙이 개선되면 과거 스냅샷을 다시 진단해
예측이 맞았는지 확인해야 한다 (예측 -> 검증 -> 학습 루프).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.diagnosis import diagnose, registry
from app.diagnosis.explainer import explain
from app.schemas.diagnosis import DiagnosisResult
from app.schemas.telemetry import TelemetrySnapshot
from app.services import scan_service

router = APIRouter()


def _run(snapshot: TelemetrySnapshot, with_explanation: bool) -> DiagnosisResult:
    result = diagnose(snapshot)
    if with_explanation:
        result.explanation = explain(result)
    return result


@router.get("/rules")
def list_rules() -> list[dict]:
    """등록된 진단 규칙 목록. 어떤 근거로 판정하는지 사용자에게 공개한다."""
    return [
        {
            "rule_id": rule_id,
            "title": cls.title,
            "requires": list(cls.requires),
        }
        for rule_id, cls in registry().items()
    ]


@router.post("/analyze", response_model=DiagnosisResult)
def analyze(
    snapshot: TelemetrySnapshot,
    explain_result: bool = Query(default=True, alias="explain"),
) -> DiagnosisResult:
    """스냅샷을 저장하지 않고 즉시 진단한다 (Estimated Scan 포함)."""
    return _run(snapshot, explain_result)


@router.post("/{snapshot_id}", response_model=DiagnosisResult)
def analyze_stored(
    snapshot_id: str,
    explain_result: bool = Query(default=True, alias="explain"),
) -> DiagnosisResult:
    snapshot = scan_service.get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="스냅샷을 찾을 수 없습니다.")
    return _run(snapshot, explain_result)
