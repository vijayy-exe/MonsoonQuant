# Methods note: basis-risk engine (M10)

**Milestone:** M10 (SPEC §7.10, part of F16). **Code:** `mq.risk.basis`.

## What this answers

The RAINCHNNAI/RAINMUMBAI futures settle on an index defined at exactly
two official stations. Anyone hedging a *different* location's rainfall
exposure with this contract takes on **basis risk**: the contract can
settle well even when their own local rain didn't track it. This module
quantifies that risk, per candidate grid cell, so a user picking a hedge
can see how much basis risk they're actually taking on before they take
it on.

## 1. Method

For each candidate cell, reconstructs a **local index**: the identical
CDR methodology (season-LPA anchor + cumulative deviation) applied to a
single-station proxy `ContractSpec` at that cell, via a thin wrapper
around `mq.pricing.burn.build_burn_sample` — the same, already-tested
M4 reconstruction logic, just pointed at one candidate cell instead of
the real two stations. Pairs the resulting 31-year local series against
the real official index series (also `build_burn_sample`, on the real
spec) and computes SPEC's six statistics: Pearson correlation, RMSE,
Kendall's τ, empirical upper/lower tail dependence (at the 80th
percentile — a crude but honest choice given a 31-year sample; SPEC
itself says "empirical", not asking for a parametric copula fit at this
scale), and hedge effectiveness.

**Hedge effectiveness doubles as M9's hedge-optimiser building block**:
`h* = Cov(L,X)/Var(X)`, `effectiveness = 1 - Var(L-h*X)/Var(L)` is
exactly the min-variance formula SPEC's `mq.risk.hedge` needs — this
module's (local rain, contract index) year-pairs are the "joint
scenarios ... from basis engine" that hedge optimiser's own spec entry
names as a prerequisite input.

## 2. Real results

Real run, RAINCHNNAI, all 31 historical seasons, a ~1°×1° box around
the two official stations (meenambakkam 12.99°N 80.18°E, nungambakkam
13.07°N 80.24°E) — 12 real IMD grid cells, each independently
reconstructed:

| cell (lat, lon) | corr | RMSE (mm) | Kendall τ | tail_upper | tail_lower | hedge eff. | h* |
|---|---|---|---|---|---|---|---|
| (13.25, 80.25) — nearest nungambakkam | 0.964 | 112.8 | 0.849 | 0.833 | 0.833 | 0.929 | 1.023 |
| (13.00, 80.00) — nearest meenambakkam | 0.961 | 112.8 | 0.811 | 1.000 | 0.833 | 0.923 | 0.977 |
| (13.25, 80.00) | 0.909 | 165.3 | 0.755 | 0.667 | 0.667 | 0.827 | 0.936 |
| (13.00, 79.75) | 0.906 | 204.5 | 0.729 | 0.500 | 0.667 | 0.821 | 1.000 |
| ... (8 more cells) | | | | | | | |
| (13.50, 79.75) — box's far corner | 0.734 | 268.0 | 0.574 | 0.667 | 0.833 | 0.538 | 0.607 |

Full table: `docs/methods/basis.md` generation script
`.scratch/basis_demo.py` / log `.scratch/basis_demo.log` (gitignored,
real-data-dependent, same pattern as other real-data demos).

**Sanity-confirms the methodology before trusting the numbers further**:
the cells geographically nearest the two real official stations have
the highest correlation (0.96+) and hedge effectiveness (0.92+) of any
cell in the box — exactly what should happen if the reconstruction is
correct, since those cells' rainfall should track the real stations'
rainfall closely. **Basis risk genuinely degrades with distance**: the
box's far corner (~0.5-0.6° away, roughly 55-65km) drops to 0.734
correlation and 0.538 hedge effectiveness — a real, substantial
reduction in how well this contract would hedge rainfall exposure even
a modest distance from Chennai proper. Tail dependence stays
comparatively high across the box (0.5-1.0) — monsoon rainfall is
regionally correlated even in its extremes, more so than the
correlation/RMSE numbers alone might suggest, though the n=31 sample
(and the 80th-percentile tail threshold it forces, for enough points to
average over) makes these numbers necessarily coarse.

## 3. What's not done yet

- **Seasonal mismatch** (`compute_basis_stats`' optional `local_daily`/
  `index_daily` parameters, measuring within-season daily co-movement
  beyond season-total correlation): implemented but not wired into
  `basis_grid`'s per-cell loop yet — doing so for every cell in a box
  needs the official index's own daily series (the real 2-station
  *average*, via `mq.forecasting.features.station_average_daily_series`)
  threaded through, not yet done.
- **GeoJSON output** (`to_geojson`) is built and tested, but the actual
  MapLibre heatmap rendering is M13 dashboard work.
- A **larger bounding box** than the real demo's modest ~1°×1° (12
  cells) would give a fuller basis-risk map — each additional cell costs
  roughly one more 31-year single-station reconstruction (~fractions of
  a second per cell at this data size), so cost scales linearly and
  isn't itself a blocker, just not run at full city-wide scale yet.
