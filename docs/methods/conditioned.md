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

## 5. Written to `valuations` for real (2026-10-11)

Previously built and demoed (§4) but never persisted — the dashboard's
Pricing page showed an explicit "not yet available" card instead of a
fake bar. Closed: a real run (h=30 days, n_paths=20,000, real as_of
2026-10-09 — the latest day with real-time rainfall on disk at the
time, `start_state=0` since that day was genuinely dry, real
`overdispersion_sd=0.3740` calibrated against the real official
index's own sd like M11's scenario lab does) gives
**fair_value=810.3mm, 90% band 340.7-1482.5mm** — written via
`mq.pricing.writer.write_valuation(method="conditioned", measure="P")`
to all 3 RAINCHNNAI series (they share one underlying index path, same
as burn/dist). Live now on `/v1/series/{id}/valuations/compare` and
the Pricing page's "Method comparison" bars, no code changes needed on
the read side — the endpoint already surfaced whatever real rows
existed.

810.3mm sits below both burn (905.6mm) and distribution (902.7mm)'s
P-measure means — a real, visible divergence from conditioning on the
current season's actual below-average recent rainfall (Oct 9's real
daily deviations were negative, see `docs/STATUS.md`), not an
unexplained outlier.

h=30 was a judgment call, not derived from data: SPEC names no single
"the" horizon, and §4's own multi-horizon table (h=7..89) shows
band90 is genuinely non-monotonic in h, so no horizon is uniquely
"best" — 30 days was chosen as a middle ground where the forecast
still carries real information (per §4's own table) while most of the
season is still carried by the simulator. Documented here rather than
silently picked.

## 6. What's not done yet

- Applying a *real* λ (vs. the illustrative one in §4) to this real
  P-measure conditioned payoff needs real settlement data — this is
  now real as of 2026-10-11 for the *burn* method (`docs/methods/
  mpr.md` §6), just not yet re-applied to the conditioned payoff
  specifically; mechanically straightforward on top of what's built
  (`mq.mpr.wang`/`esscher`'s `wang_price`/`esscher_price` on
  `result.payoff` at the real calibrated λ), not yet done since it
  would need its own `mq run`-style script rather than a one-off.
- A formal plotted band-width-vs-time figure (the table in §4 has the
  real numbers; the plot itself is `research/`-script work per M15's
  "every figure from a script" requirement).
- Only RAINCHNNAI has a real conditioned valuation; RAINMUMBAI's 2026
  season is already closed (no "remaining season" to condition a
  forecast on until Jun 2027).
