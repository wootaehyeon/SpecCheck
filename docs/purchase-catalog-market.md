# Catalog -> replacement candidates -> seller quotes -> local Gemma

## Plan

Separate authoritative part specifications from changing shopping listings.
Users should receive recommendations, not gather or enter seller information.

## Implementation

1. `component_catalog.py` validates the manufacturer-sourced catalog and merges
   optional imported feeds. Only verified, current, active products are eligible.
   Duplicate variants and inconsistent category specifications are rejected.
2. `recommendations.py` builds technical candidates from the actual snapshot and
   findings. Conditional compatibility remains conditional; seller titles cannot
   approve compatibility or add products outside this catalog.
3. `diagnosis_service.py` extracts the actual candidates' product IDs. It queries
   only those products, not the entire catalog or arbitrary browser search input.
4. `purchase_market.py` searches the official Production eBay Browse API and reads
   item details. The OAuth application token is acquired server-side with the
   client-credentials flow and renewed before expiry. A short-lived preconfigured
   application token can also be used during development.
5. Exact SKU/MPN when present, capacity and variant checks reject wrong products,
   ambiguous variants, accessories, used/refurbished items and auctions. Expired
   listings are rejected. Matching a seller title is not proof of authenticity.
6. Shipping is accepted only when the estimate explicitly targets Korea, quantity
   one, and the same currency as the item. Missing estimates are not free shipping.
   Only estimated-in-stock items with known shipping enter total-price comparison.
7. Compare by product and native currency. Taxes/customs are excluded; no fabricated
   KRW exchange rate. Only a bounded set of search results is inspected, so the
   result is never described as the cheapest offer across the entire market.
8. Local Gemma gets numeric quote context before recommending a candidate. Seller
   descriptions/titles are not injected into prompts. Failed quote lookup does not
   stop diagnosis or invent a price. All technical alternatives remain available;
   only one is marked recommended. The UI collapses alternatives initially.
9. Browser UI is read-only: recommendations, prices, caveats and shopping links.
   The old seller-input form and write routes are removed. Historical manual
   observations in SQLite are not deleted, but are not used for recommendations.

## Developer Setup

Set `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` in `backend/.env` (or deployment
secret variables), then restart the backend. Alternatively set `EBAY_OAUTH_TOKEN`.
Do not paste keys into chat, commit `.env`, put them in `NEXT_PUBLIC_*` variables,
hardcode them, or distribute a developer secret inside an installer. A released
desktop client needs a trusted server-side broker if sharing developer credentials.
API account permissions/Production eligibility must be available as well.

No credentials: `mode=technical_only`, no outbound calls, technical recommendations
continue with price/stock unconfirmed. End users are never asked to configure keys.
401/403, rate limits, timeouts and malformed responses become price-unavailable
states. Remote response bodies and credentials are not returned to the browser.
There is no unauthenticated scraper fallback in this purchase recommendation flow.
Other legacy pricing features are outside this change.

## API and Cache

`GET /api/purchase/quotes?product_id=<catalog-id>` (repeat up to 32 IDs).
Unknown catalog IDs are rejected; no arbitrary URLs or query text are accepted.
Empty IDs perform no search. Each product searches ten summaries and inspects at
most three detail records. Four workers share a bounded deadline; request redirects
are disabled. Successful/no-match quotes cache for 30-600 seconds (default 300),
temporary failures for 30 seconds. Credential and catalog fingerprints isolate
caches. Quote content changes invalidate the stored UI diagnosis. Prices are cached
in memory; diagnosis results persist in SQLite. Token-fetch errors are not prices.

The screen checks prices again every five minutes while visible. A recommendation
refresh reuses the exact snapshot and cached quotes when still valid, without
starting another hardware scan. Displayed timestamps identify the quote's age.

## Verification

Automated tests cover credential-free operation with network forbidden, OAuth token
expiry, headers/filter/destination, exact variant matching, no assumed shipping,
stock uncertainty, auctions/used/accessories, expired listings, API error handling,
cache expiry/config changes, catalog-only lookup, candidate-only diagnosis queries,
and retained alternatives. API responses are mocked for authenticated tests.

Local-only `/?preview=purchase` provides a labeled UI fixture without injecting
faults into the actual PC or generating fake prices. Manual input controls no
longer exist. Live authenticated price lookup cannot be verified until credentials
are configured. The existing catalog is still finite; expand it through reviewed
feeds (see `component-catalog.md`), not unverified seller listings.

Official references:
- https://developer.ebay.com/develop/api/buy
- https://developer.ebay.com/api-docs/buy/api-browse.html
