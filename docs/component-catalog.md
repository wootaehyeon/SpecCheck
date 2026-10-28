# Reviewed component catalog

## Changes

The old eight-item JSON and fixed selection priorities have been replaced by a
validated specification dataset with explicit product variants. The bundled feed
contains 17 records, of which 16 were reviewed for their recorded identity,
capacity, interface, and physical format. T500 remains unverified because full
official specification retrieval was blocked during this review; it is retained
for subsequent review but excluded from recommendations. Reviews are not stock,
price, reliability, compatibility, or whole-market popularity guarantees.

Structured fields include manufacturer, model number where known, capacity,
interface, form factor, memory generation, kit module count, optional profile
speed, source URL, source label, review date, review status, and lifecycle.
Unknown model numbers are left null instead of invented. Capability metadata
must agree with category. Duplicate IDs/variants and future review dates fail
validation. A source URL and a declared verification flag are not automatic proof:
the operator importing a feed must actually review its manufacturer evidence.

Unverified, discontinued, or stale records (default review age: 365 days) are not
recommended. `listed` means listed in the specifications dataset, not currently
in stock. Catalogs are sorted by capacity and stable product identity; there is
no hand-assigned brand priority or implicit price/performance ranking.

The recommendation service consumes a single catalog snapshot per diagnosis.
All matching memory kits can reach Gemma instead of only the first one. Physical
memory fit remains conditional when collector evidence is insufficient. Catalog
content or eligibility changes invalidate stored diagnosis results; unchanged
catalogs still reuse them. No manufacturer requests run during a user's scan.

## Import And Update

From the project root:

```powershell
node scripts/run-python.mjs backend -m app.services.component_catalog --schema
node scripts/run-python.mjs backend -m app.services.component_catalog C:\data\reviewed-products.json
```

Input envelope:

```json
{
  "schema_version": "1.0",
  "version": "supplier-reviewed-2026-09-28",
  "products": []
}
```

The products array must contain at least one validated product. Use the generated
schema and the bundled feed for record structure. Import validates the entire
file before atomically replacing `backend/data/catalog/imported.json`. An invalid
feed leaves the previous file unchanged. The override feed augments bundled
products and overrides matching IDs. To retire a bundled product, import its
record with `lifecycle: "discontinued"`. A new import replaces the previous
override feed, so include all overrides that should remain in force.

Optional backend settings:

```dotenv
COMPONENT_CATALOG_FILE=C:/data/reviewed-products.json
CATALOG_REVIEW_MAX_AGE_DAYS=365
```

Validated updates are read on the next diagnosis request without restarting the
server or editing recommendation code. New backend code itself still requires
server restart. The import command has no web-facing write endpoint and does not
fetch arbitrary URLs, crawl shops, install products, or fabricate specifications.

## Sources And Limits

- SN850X capacity/SKU variants: https://documents.sandisk.com/content/dam/asset-library/en_us/assets/public/western-digital/product/internal-drives/wd-black-ssd/data-sheet-wd-black-sn850x-nvme-ssd.pdf
- P41: https://ssd.skhynix.com/kr/platinum_p41/
- SATA 870 EVO: https://image.semiconductor.samsung.com/resources/data-sheet/Samsung_SSD_870_EVO_Data_Sheet_Rev1.1.pdf
- DDR4/DDR5 kits: exact Kingston datasheets linked per product.

This is an expandable reviewed local dataset, not a complete worldwide catalog.
Automatic supplier synchronization requires an agreed structured feed and access
credentials; none were supplied. Shopping title matching does not establish
socket, module, heatsink, firmware, or slot compatibility. Live price-based
ranking and platform replacement are separate work. Existing collector data
does not fully identify laptop memory fit; all imported products must continue
to respect conditional checks. There is no fake price or availability fallback.

Tests cover schema rejection, duplicate rejection, atomic failed import retention,
live reload/revision changes, expiration, unverified/discontinued filtering,
retiring bundled records, multiple memory candidates, and existing diagnostic
behavior. No test feed is imported into the live catalog.

2026-09-28 verification: 120 Backend tests passed. The Windows backend was
restarted while collection was inactive; the real latest diagnosis endpoint
returned `complete`, with no artificially injected purchase findings.
