# Methods note: forecast-conditioned pricing (M8)

**Milestone:** M8 (SPEC §7.7, F13). **Code:** `mq.pricing.conditioned`.

## What this answers

SPEC's diagram:

```
observed_to_date + forecast quantiles for next h days + simulator for remainder
                   v (quantile-mapping of simulated near-term totals to forecast)
           forecast-conditioned payoff distribution (P) -> apply lambda -> Q price + band
```

The M5 simulator is a good *generative* model of day-to-day rainfall
structure (wet/dry persistence, realistic spell lengths, a calibrated
seasonal-total variance via the overdispersion fix) but has no way to
know "it's been drier than usual the last two weeks" — it only knows
calendar day-of-year and the covariates baked into its GLM fit. A
forecast (M7's ladder) *does* carry that information, but only
usefully for a short horizon. This module gets both: trust the
forecast for the near term, trust the simulator's generative structure
for the far term, and splice them by **quantile-mapping** the
simulator's own near-term output onto the forecast's marginal
distribution.

## 1. The splice mechanism (`quantile_map`)

Rank-based CDF matching: each simulated near-term total's own empirical
percentile (plotting position `rank/(n+1)`, the same convention
`mq.mpr.wang` uses) is looked up against the forecast's quantile
function (linearly extrapolated past the fitted grid — the identical
construction `mq.forecasting.lgbm_quantile.samples_from_quantile_grid`
uses, factored out as `extrapolated_quantile_grid` so there's one
implementation, not two). This **preserves the simulator's path-for-path
ordering** (and hence its autocorrelation/spell-length structure) while
replacing its marginal distribution with the forecast's.

## 2. No simulator change needed for the near-term/remainder split

Every RNG draw in both simulator backends (M5) is a pure function of
`(seed, path_id, day_index)` — never of total `n_days`. Running
`simulate()` twice with the same seed and `start_date`, once for
`n_days=h` and once for the full remaining window, gives path-for-path
identical first-`h`-day draws between the two calls. Subtracting the
short run's terminal deviation from the long run's isolates exactly the
remainder's contribution, with zero changes to `mq.pricing.simulator`/
`simulator_ref`. Verified in `tests/unit/test_conditioned.py` via a
large-n_paths law-of-large-numbers check against each run's closed-form
expected deviation.

## 3. Why plain climatology for "forecast quantiles for next h days"

`mq.forecasting.climatology.remaining_rain_climatology_2station` (new):
the 2-station-averaged-series counterpart to `clim_v1`'s single-station
function (left untouched — it's ledger-live), with an optional
`max_horizon_days` cap. Plain climatology, not `enso_clim_v1`/
`analog_v1`/an LightGBM rung — M7's own real walk-forward backtest
(`docs/methods/forecasting.md`) found plain climatology had the best
CRPS of all 5 built rungs at this sample size. Using it here is the
data-driven choice this project's own evidence supports.

## 4. Real end-to-end run

Real chain model (M5.1, fit on the real 2-station averaged series),
real LPA, real ONI/DMI, real `observed_to_date` = 815.3mm as of
2026-10-03 (the live CDR value from `docs/STATUS.md`'s "Live state").
The settle price used to illustrate λ is **not real market data** —
there is still no real NCDEX settlement feed (bhavcopy bot-gate, same
as M2/M6) — fixed at a single hypothetical 950mm across every horizon,
purely to show how λ moves with `h`, not as a market observation.

| h (days) | n analog years | P-mean | **90% band width** | illustrative Wang λ |
|---|---|---|---|---|
| 7 | 31 | 806.9mm | 1171.5mm | 0.368 |
| 14 | 31 | 805.4mm | 1175.1mm | 0.373 |
| 30 | 31 | 819.8mm | 1124.6mm | 0.354 |
| 60 | 31 | 842.9mm | **1420.4mm** | 0.251 |
| 89 (full season) | 31 | 836.2mm | 1240.4mm | 0.310 |

**The band width is genuinely non-monotonic in `h`** — it dips slightly
from h=7 to h=30, then jumps sharply at h=60 before narrowing again at
h=89 (the full remaining season). This is exactly SPEC's own stated
expectation ("never assume monotonic shrinking uncertainty; plot band
width vs time and let data speak") confirmed on real data, not merely
a theoretical caveat written in to cover for an untested assumption.
The h=60 spike is plausible on its face: NE monsoon rainfall late in
the season (into Nov/Dec) is exactly where ENSO-linked variability is
largest for Chennai, so a window that captures more of that
higher-variance late stretch without yet averaging across the *whole*
season (which the h=89 case does, pulling the band back in via
additional averaging) can legitimately show a local maximum — a
plausible explanation, not a verified one; worth a dedicated research
note once a longer real backfill is available.

Script + full output: `.scratch/conditioned_demo.py` /
`.scratch/conditioned_demo.log` (gitignored, real-data-dependent, same
pattern as the other real-data demo scripts this project has used).

## 5. What's not done yet

- Applying a *real* λ (vs. the illustrative one above) needs real
  settlement data — blocked on the bhavcopy bot-gate, same as M6.
- The Q-measure band (not just the P-measure band shown above) would
  come from `mq.mpr.wang`/`esscher`'s own `wang_price`/`esscher_price`
  applied to `result.payoff` at the calibrated λ — mechanically
  straightforward on top of what's built here, not implemented as a
  separate reporting function yet since there's no real λ to report.
- A formal plotted band-width-vs-time figure (the table above has the
  real numbers; the plot itself is `research/`-script work per M15's
  "every figure from a script" requirement).
