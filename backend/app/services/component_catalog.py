"""Validated, replaceable product specifications; shopping listings are not specs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.core.config import PROJECT_ROOT, get_settings

SEED = PROJECT_ROOT / "backend" / "data" / "component_catalog.json"


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,100}$")
    category: Literal["memory", "storage"]
    manufacturer: str = Field(min_length=1)
    name: str = Field(min_length=1)
    model_number: str | None = None
    capacity_gb: int = Field(gt=0, le=65536)
    form_factor: Literal["UDIMM", "SODIMM", "M.2 2230", "M.2 2242", "M.2 2280", "2.5 inch"]
    interface: Literal["NVMe", "SATA"] | None = None
    memory_generation: Literal["DDR4", "DDR5"] | None = None
    module_count: int | None = Field(default=None, gt=0, le=8)
    speed_mts: int | None = Field(default=None, gt=0)
    source_url: HttpUrl
    source_label: str = Field(min_length=1)
    reviewed_at: date | None = None
    review_status: Literal["verified", "unverified"] = "unverified"
    lifecycle: Literal["listed", "discontinued"] = "listed"

    @model_validator(mode="after")
    def validate_specs(self):
        if self.source_url.scheme != "https":
            raise ValueError("specification sources must use HTTPS")
        if self.review_status == "verified" and (self.reviewed_at is None or self.reviewed_at > date.today()):
            raise ValueError("verified products require a non-future review date")
        if self.category == "memory":
            if not self.memory_generation or not self.module_count or self.form_factor not in {"UDIMM", "SODIMM"} or self.interface:
                raise ValueError("memory requires generation, module count and memory form factor")
            if self.capacity_gb % self.module_count:
                raise ValueError("memory kit capacity must divide by module count")
        elif not self.interface or self.form_factor in {"UDIMM", "SODIMM"} or self.memory_generation or self.module_count:
            raise ValueError("storage requires interface and storage form factor")
        if self.interface == "NVMe" and self.form_factor == "2.5 inch":
            raise ValueError("consumer NVMe catalog does not support 2.5 inch drives")
        return self

    def recommendation_data(self) -> dict:
        data = self.model_dump(mode="json")
        data["search_query"] = " ".join(filter(None, [self.name, self.model_number]))
        data["specifications"] = [self.memory_generation or self.interface, f"{self.capacity_gb}GB", self.form_factor]
        if self.module_count:
            data["specifications"].append(f"{self.capacity_gb // self.module_count}GB x {self.module_count}")
        if self.speed_mts:
            data["specifications"].append(f"{self.speed_mts}MT/s (profile support must be checked)")
        data["specifications"].append(f"Spec reviewed: {self.reviewed_at}")
        return data


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    version: str = Field(min_length=1)
    products: list[Product] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({product.id for product in self.products}) != len(self.products):
            raise ValueError("duplicate product IDs")
        identities = [(p.manufacturer.lower(), (p.model_number or p.name).lower(), p.capacity_gb, p.form_factor) for p in self.products]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate product variants")
        return self


def override_path() -> Path:
    return get_settings().component_catalog_file or get_settings().data_dir / "catalog" / "imported.json"


def load_catalog() -> tuple[list[dict], str]:
    seed = Catalog.model_validate_json(SEED.read_text(encoding="utf-8"))
    products = {product.id: product for product in seed.products}
    path = override_path()
    if path.exists():
        imported = Catalog.model_validate_json(path.read_text(encoding="utf-8"))
        products.update({product.id: product for product in imported.products})
    Catalog(schema_version="1.0", version="merged", products=list(products.values()))
    canonical = json.dumps([products[key].model_dump(mode="json") for key in sorted(products)], sort_keys=True)
    revision = hashlib.sha256(canonical.encode()).hexdigest()
    max_age = max(0, get_settings().catalog_review_max_age_days)
    eligible = [p for p in products.values() if p.review_status == "verified" and p.lifecycle == "listed"
                and p.reviewed_at and (date.today() - p.reviewed_at).days <= max_age]
    # Expiration invalidates results without forcing fresh AI generation every day.
    revision = hashlib.sha256((revision + json.dumps(sorted(p.id for p in eligible))).encode()).hexdigest()
    eligible.sort(key=lambda p: (p.capacity_gb, p.name.lower(), p.id))
    return [p.recommendation_data() for p in eligible], revision


def import_catalog(source: Path) -> int:
    catalog = Catalog.model_validate_json(source.read_text(encoding="utf-8"))
    seed = Catalog.model_validate_json(SEED.read_text(encoding="utf-8"))
    merged = {product.id: product for product in seed.products}
    merged.update({product.id: product for product in catalog.products})
    Catalog(schema_version="1.0", version="merged", products=list(merged.values()))
    target = override_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Validate the whole feed before replacing it; readers see old or new data.
    fd, temporary = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(catalog.model_dump_json(indent=2))
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return len(catalog.products)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate and import a reviewed product catalog feed")
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()
    if args.schema:
        print(json.dumps(Catalog.model_json_schema(), indent=2))
    elif args.source:
        print(f"Imported {import_catalog(args.source)} products")
    else:
        parser.error("provide a catalog JSON file or --schema")
