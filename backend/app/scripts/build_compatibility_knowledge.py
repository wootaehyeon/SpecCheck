"""Normalize the vendored CC BY 4.0 dataset; retain attribution, never editorial claims."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "datasets" / "compatibility"
OUTPUT = ROOT / "backend/app/diagnosis/knowledge/compatibility.json"


def build():
    source = DATA / "techfuelhq/pc-builder-parts.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    curated = DATA / "manufacturer-boards.json"
    fields = ("id", "vendor", "model", "socket", "ram_type", "ram_slots", "ram_max_gb", "m2_slots", "source", "last_verified")
    boards = [{**{k: b[k] for k in fields if k in b}, "verification": "dataset_reported"}
              for b in data["motherboard"] if b.get("source", "").startswith("https://")]
    boards.extend(json.loads(curated.read_text(encoding="utf-8"))["boards"])
    cpus = [{k: c[k] for k in ("id", "vendor", "model", "socket", "source", "last_verified") if k in c}
            for c in data["cpu"] if c.get("source", "").startswith("https://")]
    artifact = {"schema_version": 1, "attribution": data["_meta"]["attribution_required"],
                "license": "CC BY 4.0", "source_url": "https://github.com/iBlessi/pc-builder-parts",
                "source_git_blob": "2a75867059d06e9bdd31e2408af7b64eca3ae286",
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "curated_sha256": hashlib.sha256(curated.read_bytes()).hexdigest(),
                "boards": boards, "cpus": cpus}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Built {len(boards)} boards and {len(cpus)} CPU socket records: {OUTPUT.name}")


if __name__ == "__main__":
    build()
