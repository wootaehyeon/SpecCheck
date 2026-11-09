# Estimate planner

The legacy web estimate flow uses `frontend/web/js/estimate-engine.js`.
Prices are supplied by the market API or entered explicitly by the user.
No catalog or capacity-based example prices are supplied. Missing candidate
prices disable application, including RAM kits. The v3 price storage key avoids
reusing previously seeded demo candidate prices.
No random FPS, compatibility score, purchase risk, discount percentage or
benchmark improvement is generated. The analysis calls `/api/evaluate-build`
alongside `/api/market-prices`. Registered benchmark values and backend
compatibility issues are displayed as server calculations, separate from local
measurements. Unregistered models show no benchmark score. Price lookup failure,
foreign currency and demo sources cannot produce a won comparison. A lowest
price does not require an average price. Navigation preserves actual API results;
changed builds invalidate evaluation and changed parts lose their old quotations.
Old stored analysis results are invalidated using a version and build signature.
The market research page also returns empty states instead of sample posts,
prices or sentiment. See [real environment validation](validation-2026-11-09.md).

The planner compares whole-build cost after replacing one part, checks the
budget, CPU socket, DDR generation, GPU manufacturer PSU requirement and CUDA
constraint. BIOS, cooler, board QVL, GPU dimensions and connectors remain
explicit unverified checks. Applying a candidate updates the stored estimate;
undo restores the previous estimate. Candidates are independent alternatives,
not a claim that all can be purchased within the same budget simultaneously.

Workload targets (RAM, VRAM and core count) are planning heuristics, not game
benchmarks or universal application minimum specifications. Candidates improve
those specific requirements, not guaranteed speed. Conservative GPU comparison
pairs prevent selecting a lower family merely for more VRAM. No candidate is
preferred solely because it was released later.

The initial catalog is deliberately bounded to the listed verified models.
Unknown models and ambiguous memory variants are not fuzzy-matched. Extend
the catalog with reviewed manufacturer sources before supporting more models.
Each entry records the manufacturer's source URL. Specifications were checked
on 2026-10-30 using NVIDIA RTX 4060 / RTX 5060 / RTX 5070 family pages and AMD
Ryzen 7500F / 9600X / 9700X and RX 9060 XT product pages. Legacy GPU CSV data
is not used: inspected rows contain mismatched model/chip specifications.

Run regression checks with:

```
node --test scripts/test-legacy-market-prices.mjs
```

Browser checks: QHD / 1,200,000 KRW yields conditional VRAM candidates;
insufficient PSU/budget disables application; applying a 450,000 KRW GPU
instead of the original 430,000 KRW changes 1,040,000 to 1,060,000 KRW;
undo restores the previous build. All candidate prices in these tests are explicit
test inputs. Run `npx playwright test estimate.spec.cjs assembly.spec.cjs` from
`frontend/tests`, with `SPECCHECK_TEST_PYTHON` pointing to the backend Python,
`MONITOR_TEST_BROWSER=msedge` if using installed Edge, and an available
`SPECCHECK_TEST_PORT` (default 8031).
