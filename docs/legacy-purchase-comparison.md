# Reusing the legacy purchase workflow

## History inspected

- `c1b533a` (2026-06-11): eBay used-price lookup, save/upgrade optimization,
  current-versus-replacement parts, savings summaries, benchmark comparison and
  listing links in the old HTML/JavaScript recommendation page.
- `46b340c`: later hardcoded demo market/optimization results.

The old backend services still exist (`ebay_api.py`, `used_price_optimizer.py`),
but their unauthenticated scraping, fixed FX fallback and fuzzy benchmark-based
CPU/GPU replacement are NOT called by the diagnostic purchase screen. Legacy
endpoints elsewhere remain unchanged. This is a scoped workflow port, not a merge
or restoration of the old mock-data page.

## Restored in the current UI

- Cost/effect mode controls inspired by the old save/upgrade view.
- Side-by-side collected hardware and catalog replacement parts.
- Complete shipping-included candidate totals and differences against the
  recommended candidate, only in a common native currency.
- Direct validated listing links when available; exact product eBay search links
  otherwise. Unconfirmed prices are not zero or fabricated savings.
- Replacement benefits from candidate reasons and passed checks; conditional
  compatibility checks stay under purchase cautions, never become advantages.
- Collected components outside the replacement list are shown, without assuming
  uncollected parts or guaranteeing a platform migration's compatibility.
- Detailed listings collapsed beneath the estimate table to reduce repetition.

## Limits

No percentages for SSD speed/FPS or CPU/GPU benchmark gains are invented. Current
candidates are memory/storage; the historical CPU/GPU same-budget performance
optimizer needs verified CPU/GPU specifications, benchmark provenance, budget and
compatibility integration before it can become a diagnostic replacement engine.
Cost differences are relative to a fully quoted recommended replacement, not to
the original PC's unknown historical purchase price. Taxes/customs/labor are
excluded. Multiple collected drives require a separate target-device check.

`/?preview=purchase` compares 1TB and 2TB specification-backed example candidates,
labels the snapshot as example data, and generates no demo price or stock records.
Authenticated eBay retrieval is still conditional on developer credentials.

## Verification

Pure UI tests cover complete multi-part totals, lowest matching quotes, cents
arithmetic, missing shipping, uncertain stock, stale/invalid quotes, mixed
currencies, empty estimates, actual inventory and grounded benefit statements.
Existing backend and UI tests are retained.
