from datetime import date, timedelta
import json

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.services import component_catalog as catalog


@pytest.fixture(autouse=True)
def isolated_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "component_catalog_file", tmp_path / "imported.json")


def product(**overrides):
    value = {"id": "imported-ssd-2tb", "category": "storage", "manufacturer": "Fixture",
             "name": "Fixture 2TB", "model_number": "FIX-2TB", "capacity_gb": 2000,
             "interface": "NVMe", "form_factor": "M.2 2280", "source_url": "https://example.com/spec",
             "source_label": "Test fixture", "review_status": "verified", "reviewed_at": str(date.today())}
    return {**value, **overrides}


def feed(tmp_path, products):
    source = tmp_path / "feed.json"
    source.write_text(json.dumps({"schema_version": "1.0", "version": "test", "products": products}), encoding="utf-8")
    return source


def test_seed_has_reviewed_capacity_variants_and_no_priority_rank():
    products, _ = catalog.load_catalog()
    assert any(p['interface'] == 'SATA' for p in products)
    assert any(p['capacity_gb'] == 4000 for p in products)
    assert len([p for p in products if p['category'] == 'memory']) >= 4
    assert all('selection_priority' not in p for p in products)
    assert not any(p['id'] == 'crucial-t500-1tb' for p in products)


def test_import_is_immediately_visible_and_changes_revision(tmp_path):
    _, before = catalog.load_catalog()
    assert catalog.import_catalog(feed(tmp_path, [product()])) == 1
    products, after = catalog.load_catalog()
    assert before != after
    assert any(p['id'] == 'imported-ssd-2tb' for p in products)
    catalog.import_catalog(feed(tmp_path, [product(capacity_gb=4000, name='Fixture 4TB')]))
    assert catalog.load_catalog()[1] != after


def test_invalid_import_keeps_previous_feed(tmp_path):
    catalog.import_catalog(feed(tmp_path, [product()]))
    before = catalog.override_path().read_bytes()
    with pytest.raises(ValidationError):
        catalog.import_catalog(feed(tmp_path, [product(), product()]))
    assert catalog.override_path().read_bytes() == before


@pytest.mark.parametrize('changes', [
    {'review_status': 'unverified'}, {'lifecycle': 'discontinued'},
    {'reviewed_at': str(date.today() - timedelta(days=366))},
])
def test_unreviewed_expired_and_discontinued_products_are_excluded(tmp_path, changes):
    catalog.import_catalog(feed(tmp_path, [product(**changes)]))
    assert not any(p['id'] == 'imported-ssd-2tb' for p in catalog.load_catalog()[0])


@pytest.mark.parametrize('changes', [
    {'capacity_gb': 0}, {'interface': None}, {'form_factor': 'UDIMM'},
    {'reviewed_at': None}, {'reviewed_at': str(date.today() + timedelta(days=1))},
    {'source_url': 'http://example.com/spec'}, {'selection_priority': 1},
])
def test_inconsistent_or_unproven_metadata_is_rejected(changes):
    with pytest.raises(ValidationError):
        catalog.Product.model_validate(product(**changes))


def test_import_can_retire_a_seed_product(tmp_path):
    seed = catalog.Catalog.model_validate_json(catalog.SEED.read_text(encoding='utf-8'))
    retired = seed.products[0].model_dump(mode='json')
    retired['lifecycle'] = 'discontinued'
    catalog.import_catalog(feed(tmp_path, [retired]))
    assert not any(p['id'] == retired['id'] for p in catalog.load_catalog()[0])


def test_import_cannot_duplicate_seed_sku_under_a_new_id(tmp_path):
    seed = catalog.Catalog.model_validate_json(catalog.SEED.read_text(encoding='utf-8'))
    duplicate = seed.products[0].model_dump(mode='json')
    duplicate['id'] = 'duplicate-sku-alias'
    with pytest.raises(ValidationError):
        catalog.import_catalog(feed(tmp_path, [duplicate]))
    assert not catalog.override_path().exists()
