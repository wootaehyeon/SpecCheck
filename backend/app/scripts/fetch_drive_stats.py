"""Download ONE daily member via HTTP ranges, never the multi-GB archive.

Backblaze source/terms: https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data
Only anonymous SMART counters are retained. The failure flag is deliberately NOT
used as a replacement/repair label. Imported inputs receive weak teacher labels.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import random

from remotezip import RemoteZip

URL = "https://f001.backblazeb2.com/file/Backblaze-Hard-Drive-Data/data_Q1_2024.zip"


def fetch(output):
    with RemoteZip(URL, timeout=60) as archive:
        member = sorted(n for n in archive.namelist() if n.endswith("2024-01-01.csv") and "__MACOSX" not in n)[0]
        payload = archive.read(member)
    rng = random.Random(20261118)
    sample, usable, total = [], 0, 0
    for row in csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))):
        total += 1
        if not row.get("smart_5_raw") or not row.get("smart_197_raw"):
            continue
        values = {"reallocated_sectors": float(row["smart_5_raw"]), "pending_sectors": float(row["smart_197_raw"])}
        usable += 1
        # Reservoir sample avoids taking only the first manufacturer's drives.
        if len(sample) < 5000:
            sample.append(values)
        else:
            index = rng.randrange(usable)
            if index < len(sample): sample[index] = values
    result = {"source": "Backblaze Drive Stats", "source_url": URL, "member": member,
              "source_sha256": hashlib.sha256(payload).hexdigest(), "source_rows": total, "usable_rows": usable,
              "sampling": "seed=20261118; uniform reservoir, max 5000; no serial numbers",
              "label_source": "legacy_rule_weak_supervision; failure flag not used",
              "terms_url": "https://www.backblaze.com/cloud-storage/resources/hard-drive-test-data",
              "rows": sample}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("../datasets/diagnosis/backblaze-smart-sample.json"))
    fetch(parser.parse_args().output)
