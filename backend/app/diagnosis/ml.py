"""Inference from fitted CART models exported as JSON (no pickle or runtime training)."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from app.diagnosis.ml_features import FEATURES, FEATURE_VERSION, extract
from app.schemas.diagnosis import Evidence, Finding, SEVERITY_WEIGHT

MODEL_PATH = Path(__file__).with_name("models") / "diagnosis-v1.json"


@lru_cache(maxsize=1)
def load_model():
    raw = MODEL_PATH.read_bytes()  # Missing/corrupt model must fail visibly; never fall back to rules.
    artifact = json.loads(raw)
    if artifact["feature_version"] != FEATURE_VERSION or set(artifact["models"]) != set(FEATURES):
        raise ValueError("Diagnosis model feature contract mismatch; retrain the model.")
    for key, model in artifact["models"].items():
        if model["features"] != list(FEATURES[key]):
            raise ValueError(f"Feature order mismatch: {key}")
    return artifact, hashlib.sha256(raw).hexdigest()


def model_version():
    return load_model()[1]


def predict(model, values):
    node = 0
    tree = model["tree"]
    while tree[node][0] >= 0:
        feature, threshold, left, right = tree[node]
        node = left if values[feature] <= threshold else right
    _, label, score, _ = tree[node]
    return label, score


def predict_findings(snapshot, rule_ids=None):
    artifact, _ = load_model()
    findings = []
    for key, rows in extract(snapshot).items():
        if rule_ids and key not in rule_ids:
            continue
        model = artifact["models"][key]
        candidates = []
        for values, source, raw in rows:
            label, score = predict(model, values)
            if label == "none":
                continue
            template = model["labels"][label]
            confidence = template["confidence"]
            if key.startswith("RL-") and snapshot.data("reliability").get("log_covers_window") is False:
                confidence = round(confidence * 0.8, 2)
            if key == "HW-DISK-001":
                confidence = 0.85 if raw.get("identified") else 0.5
            summary = template["title"] + " 가능성을 학습 모델이 감지했습니다. 측정 근거를 확인하세요."
            if key == "PF-CPU-001":
                processes = snapshot.data("performance").get("top_processes") or []
                if processes:
                    summary += " 상위 프로세스: " + str(processes[0].get("name", ""))
            evidence = [Evidence(source=source, detail=", ".join(f"{name}={value:g}" for name, value in zip(model["features"], values)), value=raw)]
            if key == "PF-THROTTLE-001":
                thermal = snapshot.data("performance").get("thermal") or {}
                if thermal.get("available"):
                    evidence.append(Evidence(source="performance.thermal", detail=f"최고 온도 {thermal.get('max_c')}°C", value=thermal))
            finding = Finding(**{**template, "rule_id": key, "summary": summary, "confidence": confidence * score,
                                 "evidence": evidence, "model_score": score})
            candidates.append(finding)
        if candidates:
            findings.append(max(candidates, key=lambda f: (SEVERITY_WEIGHT[f.severity], f.confidence)))
    return findings
