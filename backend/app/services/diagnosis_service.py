"""Append-only diagnosis history, including exact input and rules fingerprint."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from app.schemas.diagnosis import DiagnosisResult
from app.schemas.telemetry import TelemetrySnapshot
from app.services.scan_service import _connect


def rules_version() -> str:
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / "diagnosis").rglob("*.py")) + [root / "schemas" / "diagnosis.py", root / "schemas" / "telemetry.py"]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def save_diagnosis(snapshot: TelemetrySnapshot, result: DiagnosisResult) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO diagnoses (diagnosis_id, snapshot_id, generated_at, rules_version, input_payload, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), snapshot.snapshot_id, result.generated_at.isoformat(), rules_version(),
             snapshot.model_dump_json(), result.model_dump_json()),
        )


def history(snapshot_id: str, limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT diagnosis_id, rules_version, payload FROM diagnoses WHERE snapshot_id = ? "
            "ORDER BY generated_at DESC, rowid DESC LIMIT ?", (snapshot_id, limit)
        ).fetchall()
    return [{"diagnosis_id": r["diagnosis_id"], "rules_version": r["rules_version"],
             "result": json.loads(r["payload"])} for r in rows]
