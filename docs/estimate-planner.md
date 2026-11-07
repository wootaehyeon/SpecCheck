# Estimate planner

The legacy web estimate flow uses `frontend/web/js/estimate-engine.js`.
Prices are explicitly marked demonstration inputs, editable in the planner.
No random FPS, compatibility score, purchase risk, discount percentage or
benchmark improvement is generated. Market averages remain unavailable.

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
undo restores the previous build.
