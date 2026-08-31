"""Scan API - Agent 스냅샷 수집 및 조회 (M3).

Agent(``speccheck-agent scan --upload``)가 이 엔드포인트로 telemetry를 보낸다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.telemetry import (
    SUPPORTED_SCHEMA_MAJOR,
    SnapshotAccepted,
    SnapshotSummary,
    TelemetrySnapshot,
)
from app.services import scan_service

router = APIRouter()


@router.post("/snapshots", response_model=SnapshotAccepted, status_code=201)
def upload_snapshot(snapshot: TelemetrySnapshot) -> SnapshotAccepted:
    """Agent가 수집한 telemetry 스냅샷을 저장한다."""
    if snapshot.schema_major != SUPPORTED_SCHEMA_MAJOR:
        raise HTTPException(
            status_code=415,
            detail="지원하지 않는 schema_version {0} (서버 지원: {1}.x). Agent를 업데이트하세요.".format(
                snapshot.schema_version, SUPPORTED_SCHEMA_MAJOR
            ),
        )

    received_at = scan_service.save_snapshot(snapshot)
    return SnapshotAccepted(
        snapshot_id=snapshot.snapshot_id,
        scan_mode=snapshot.scan_mode,
        received_at=received_at,
        usable_sections=[name for name in snapshot.sections if snapshot.section(name)],
    )


@router.get("/snapshots", response_model=list[SnapshotSummary])
def list_snapshots(
    device_id: str | None = Query(default=None, description="기기별 시계열 조회"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SnapshotSummary]:
    return scan_service.list_snapshots(device_id=device_id, limit=limit)


@router.get("/snapshots/{snapshot_id}", response_model=TelemetrySnapshot)
def get_snapshot(snapshot_id: str) -> TelemetrySnapshot:
    snapshot = scan_service.get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="스냅샷을 찾을 수 없습니다.")
    return snapshot
