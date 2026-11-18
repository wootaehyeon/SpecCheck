"""python -m app.scripts.train_diagnosis --output app/diagnosis/models/diagnosis-v1.json

Rule teachers are used ONLY here. Synthetic metrics measure teacher agreement,
not clinical accuracy or observed repair outcomes. No application tests are training data.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import itertools
import json
from pathlib import Path
import random

import sklearn
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import accuracy_score, f1_score, classification_report

from app.diagnosis import registry
from app.diagnosis.ml_features import FEATURES, FEATURE_VERSION, extract
from app.diagnosis.ml import predict
from app.schemas.telemetry import TelemetrySnapshot

# Sampling ranges and boundary coverage, not inference thresholds.
DOMAINS = {
    "speed_ratio": (0.1, 1.5, [0.79, 0.8, 0.805, 0.81, 0.8999, 0.9, 1]),
    "total_gb": (0.1, 128, [4, 7.9999, 8, 16, 32]),
    "is_hdd": (0, 1, [0, 1]), "age_days": (0, 4000, [729, 730, 1094, 1095]),
    "free_percent": (0, 100, [0, 4.9999, 5, 9.9999, 10, 50]),
    "free_gb": (0, 2000, [0, 14.9999, 15, 39.9999, 40, 160]),
    "reallocated_sectors": (0, 1000, [0, 1, 2, 9, 10, 20]),
    "pending_sectors": (0, 100, [0, 1, 2]),
    "predict_failure": (0, 1, [0, 1]),
    "wear_percent": (0, 150, [0, 69, 70, 75, 89, 90, 95]),
    "whea_corrected": (0, 1000, [0, 4, 5, 19, 20]),
    "whea_fatal": (0, 100, [0, 1, 2]),
    "crash_count": (0, 100, [0, 1, 2, 3, 4]),
    "io_error_count": (0, 100, [0, 1, 2, 9, 10, 15]),
    "committed_percent": (0, 100, [0, 89.9999, 90, 93, 96, 100]),
    "available_mb": (0, 64000, [0, 700, 1500, 1500.0001, 6000]),
    "cpu_avg": (0, 100, [0, 49.9999, 50, 69.9999, 70, 88, 100]),
    "cpu_min": (0, 100, [0, 8, 49.9999, 50, 80, 100]),
    "is_power_saver": (0, 1, [0, 1]),
    "clock_ratio": (0, 1.5, [0.22, 0.39, 0.6, 0.6001, 1]),
    "temperature": (0, 120, [0, 60, 89.9999, 90, 96]),
    "tampering_count": (0, 10, [0, 1, 2]),
    "log_gap": (0, 1, [0, 1]), "truncated": (0, 1, [0, 1]),
    "error_count": (0, 10, [0, 1, 2]),
}
INTEGERS = {"age_days", "reallocated_sectors", "pending_sectors", "wear_percent", "whea_corrected", "whea_fatal", "crash_count", "io_error_count", "tampering_count", "error_count"}
BOOLEANS = {"is_hdd", "predict_failure", "is_power_saver", "log_gap", "truncated"}


def make_snapshot(key, values):
    v = dict(zip(FEATURES[key], values))
    hw, st, pf, rl, sec = {}, {}, {}, {}, {}
    now = datetime.now(timezone.utc)
    if key == "HW-RAM-001": hw = {"memory": {"modules": [{"rated_speed_mhz": 10000, "configured_speed_mhz": v["speed_ratio"] * 10000}]}}
    elif key == "HW-RAM-002": hw = {"memory": v}
    elif key == "HW-DISK-001": hw = {"storage": [{"media_type": "HDD" if v["is_hdd"] else "SSD"}]}
    elif key == "SW-GPU-001": hw = {"gpu": [{"driver_date": (now - timedelta(days=v["age_days"])).isoformat()}]}
    elif key == "SW-BIOS-001": hw = {"motherboard": {"bios": {"released_at": (now - timedelta(days=v["age_days"])).isoformat()}}}
    elif key == "ST-SPACE-001": st = {"volumes": [{**v, "is_system": True}]}
    elif key.startswith("ST-"): st = {"disks": [v]}
    elif key.startswith("RL-"):
        totals = v.copy()
        if key == "RL-CRASH-001": totals = {"unexpected_shutdown": v["crash_count"], "bugcheck": 0}
        if key == "RL-DISK-001": totals = {"disk_error": v["io_error_count"], "filesystem_error": 0}
        rl = {"totals": totals, "log_covers_window": True, "window_days": 30}
    elif key == "PF-MEM-001": pf = {"memory": {k: {"avg": val} for k, val in v.items()}}
    elif key == "PF-CPU-001": pf = {"cpu": {"usage_percent": {"avg": v["cpu_avg"], "min": v["cpu_min"]}}}
    elif key == "PF-POWER-001": pf = {"power_plan": v}
    elif key == "PF-THROTTLE-001": pf = {"cpu": {"clock": {"ratio": v["clock_ratio"]}, "usage_percent": {"avg": v["cpu_avg"]}}, "thermal": {"max_c": v["temperature"]}}
    elif key.startswith("SEC-"):
        events = ([25] * int(v.get("tampering_count", 0))) + ([255] * int(v.get("error_count", 0)))
        sec = {"consent": {"version": "sysmon-minimal-v1", "granted_at": now}, "window_start": now,
               "window_end": now, "log_oldest_at": now, "log_reset": False,
               "log_gap": bool(v.get("log_gap")), "truncated": bool(v.get("truncated")),
               "events": [{"event_id": e, "record_id": i+1, "occurred_at": now} for i, e in enumerate(events)]}
    sections = {k: {"status": "ok", "data": d} for k, d in zip(("hardware", "storage_health", "performance", "reliability", "security"), (hw, st, pf, rl, sec)) if d}
    return TelemetrySnapshot.model_validate({"schema_version": "1.1.0", "snapshot_id": "synthetic", "collected_at": now,
                                           "scan_mode": "actual", "agent": {"version": "training", "os": "synthetic"}, "sections": sections})


def random_values(names, rng):
    row = []
    for name in names:
        low, high, anchors = DOMAINS[name]
        if name in BOOLEANS: value = rng.choice([0, 1])
        elif rng.random() < 0.4: value = rng.choice(anchors)
        elif name in INTEGERS: value = rng.randint(low, high)
        else: value = rng.uniform(low, high)
        row.append(value)
    return row


def train(output, external=None):
    models, reports = {}, {}
    teachers = registry()
    for key, names in FEATURES.items():
        rng = random.Random(20261118)
        rows = list(itertools.product(*(DOMAINS[n][2] for n in names)))
        rows += [random_values(names, rng) for _ in range(8000)]
        external_rows = []
        if external and key == "ST-SMART-001":
            external_rows = json.loads(external.read_text(encoding="utf-8"))["rows"]
            rows += [[r["reallocated_sectors"], r["pending_sectors"]] for r in external_rows if r.get("pending_sectors") is not None and r.get("reallocated_sectors") is not None]
        rows = sorted(set(tuple(r) for r in rows))
        labels = {}

        def label(row):
            snapshot = make_snapshot(key, row)
            finding = teachers[key]().evaluate(snapshot)
            if finding is None: return "none"
            target = finding.severity.value + ":" + finding.recommended_action.value
            labels[target] = finding.model_dump(mode="json", include={"title", "axis", "severity", "recommended_action", "action_detail", "root_cause", "confidence"})
            return target

        targets = [label(r) for r in rows]
        clf = DecisionTreeClassifier(random_state=42, max_depth=12)
        clf.fit(rows, targets)
        tree = []
        for i, feature in enumerate(clf.tree_.feature):
            if feature >= 0:
                tree.append([int(feature), float(clf.tree_.threshold[i]), int(clf.tree_.children_left[i]), int(clf.tree_.children_right[i])])
            else:
                counts = clf.tree_.value[i][0]
                index = int(counts.argmax())
                tree.append([-1, str(clf.classes_[index]), float(counts[index] / counts.sum()), 0])
        model = {"features": list(names), "tree": tree, "labels": labels}
        # A separate random draw, excluding all training feature vectors.
        known = set(rows)
        validation = sorted(set(tuple(random_values(names, rng)) for _ in range(4000)) - known)
        truth = [label(row) for row in validation]
        predictions = [predict(model, row)[0] for row in validation]
        # Verify portable inference against sklearn on both sets.
        assert [predict(model, r)[0] for r in rows + validation] == list(clf.predict(rows + validation))
        reports[key] = {"training_rows": len(rows), "external_source_rows": len(external_rows), "validation_rows": len(validation),
                        "teacher_agreement": accuracy_score(truth, predictions) if truth else None,
                        "macro_f1": f1_score(truth, predictions, average="macro", zero_division=0) if truth else None,
                        "classes": classification_report(truth, predictions, output_dict=True, zero_division=0) if truth else {},
                        "note": "Independent synthetic feature vectors; not real-world accuracy. Finite domains may be exhausted by training."}
        models[key] = model
        print(key, reports[key]["training_rows"], reports[key]["teacher_agreement"], flush=True)
    teacher_hash = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(Path(__file__).parents[1].joinpath("diagnosis/rules").glob("*.py")))).hexdigest()
    artifact = {"feature_version": FEATURE_VERSION, "algorithm": "sklearn.tree.DecisionTreeClassifier", "sklearn_version": sklearn.__version__,
                "label_source": "legacy_rule_weak_supervision", "seed": 20261118, "teacher_sha256": teacher_hash, "models": models}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    report_path = output.with_suffix(".report.json")
    report_path.write_text(json.dumps({"models": reports, "real_outcome_validation": False,
                                     "external_source": str(external) if external else None}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("app/diagnosis/models/diagnosis-v1.json"))
    parser.add_argument("--external", type=Path)
    args = parser.parse_args()
    train(args.output, args.external)
