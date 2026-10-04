# Methods note: historical burn analysis and index-distribution pricing

**Milestone:** M4 (SPEC §7.3, F08/F09). **Code:** `mq.pricing.burn`,
`mq.pricing.distribution`, `mq.pricing.selection`.

## What this answers

Given a reconstructed history of the CDR index (`mq.index.engine.compute_index`,
see `docs/methods/index_engine.md` — not yet written, see M3 code docstrings
meanwhile), what's a reasonable physical-measure (P) estimate of a
RAINCHNNAI/RAINMUMBAI contract's fair value, before any market-price-of-risk
adjustment (that's M6)?

Two independent answers, per SPEC's M4 gate:

1. **Burn**: the empirical distribution of what the contract would
   actually have settled at, replayed over every historical season.
2. **Distribution fit**: a smooth (or resampled) P-measure distribution
   fit to that same burn sample, chosen by cross-validated predictive
   skill rather than visual goodness-of-fit.

## 1. Burn analysis (`mq.pricing.burn`)

For this CDR contract, the index *is* the settlement price (Final
Settlement Price = the CDR spot value on expiry day — SPEC §7.1,
`settlement.method`). So "burn" here means literally re-running
`compute_index` for every historical year through to the real period end
(Dec 31 for RAINCHNNAI, Sep 30 for RAINMUMBAI), using the real official
methodology — not an approximation of the payoff.

A year is included only if `rain_grid` has complete station coverage
from `period_start` through `period_end` for that year; any gap drops
the year silently rather than guessing a value for it
(`reconstruct_season` returns `None`). SPEC explicitly expects backfill
gaps (§8.1), so this is the correct behavior, not a bug to paper over.

**Detrending:** not implemented in this pass. RAINCHNNAI's sample (1991,
1992, ..., 2020, 2023 — the IMD/NCDEX 30-year LPA base period plus one
smoke-test year, V4) shows no visually obvious trend and n=31 is already
thin for a 3-parameter fit; adding a detrend term would cost more
degrees of freedom than it's likely worth at this sample size. Revisit
once the backfill reaches further back (RAINCHNNAI's own cited LPA base
period is 1971-2020) or forward (more post-2020 years as they're
ingested).

**Statistics computed:** mean, median, sd, P5/P25/P75/P95, skew, and the
mean of the lower/upper 5% tails (a crude expected-shortfall analogue —
"lower" and "upper" rather than a signed "loss", since whether a high or
low CDR value is a loss depends on which side of the contract a holder
is on, and this project makes no position recommendation, SPEC §1.3).

**Measured result (RAINCHNNAI, n=31, all years 1991-2020 + 2023):**

| Stat | Value (mm) |
|---|---|
| mean | 905.6 |
| median | 843.4 |
| sd | 388.5 |
| P5 | 449.6 |
| P25 | 647.9 |
| P75 | 1049.9 |
| P95 | 1699.0 |
| skew | 1.14 |
| ES (lower 5%) | 345.3 |
| ES (upper 5%) | 1952.8 |

Right-skewed, as expected for a cumulative-rainfall-linked index — a few
very wet seasons (2005: 2022.9mm, the sample maximum; 2015: 1882.8mm)
pull the upper tail out further than the lower tail is pulled in. Of the
two, only 2015 lines up with ENSO (ASO-mean ONI 2.01, a strong El Niño
year by any standard threshold); 2005's ASO-mean ONI was -0.17 —
near-neutral, not El Niño — so its wet season isn't an ENSO story. That
2015 result is exactly the kind of case the ENSO-conditioned climatology
candidate is meant to capture — see §3 for why it doesn't yet improve
CRPS at this sample size regardless.

## 2. Distribution candidates (`mq.pricing.distribution`)

Six candidates, all exposing the same interface (a large Monte-Carlo
sample for CRPS, and — where a density is actually defined — a logpdf
for diagnostic log-likelihood):

| Candidate | What it is | Has a density? |
|---|---|---|
| `gamma` | scipy MLE, free shape/loc/scale | yes |
| `lognormal` | scipy MLE, free shape/loc/scale | yes |
| `weibull` | scipy MLE (`weibull_min`), free shape/loc/scale | yes |
| `kde_silverman` | Gaussian KDE, Silverman's rule bandwidth | yes |
| `kde_cv` | Gaussian KDE, bandwidth chosen by leave-one-out log-likelihood over a grid of {0.2, ..., 1.5} x Silverman's | yes |
| `bootstrap` | resample the historical sample directly | **no** — see below |
| `enso_climatology` | empirical distribution from years sharing the target year's ONI tercile (ASO-mean ONI, from the real ingested `climate_idx` data); falls back to the full sample if the matching group has fewer than 5 years | **no** |

**Why bootstrap and ENSO-climatology have no density:** both are
resampling schemes over a finite, unsmoothed set of historical values —
there's no actual probability density to evaluate a held-out point
against (every un-resampled point not in the training set literally has
zero density under the empirical distribution). This isn't a limitation
to work around; it's honestly what those methods are. CRPS, which only
needs samples, scores them fine; log-likelihood can't.

**ENSO tercile definition:** relative to the sample itself (bottom
third / middle third / top third of ASO-mean ONI across the burn
sample's own years), not an absolute meteorological threshold — matching
SPEC's framing ("years with the same ONI tercile") rather than inventing
a fixed cutoff.

## 3. Selection (`mq.pricing.selection`)

**Rolling-origin CV, implemented as leave-one-out.** SPEC calls for
"rolling-origin CV"; with n=31 and (for the parametric candidates) 3 free
parameters each, a true walk-forward split would leave too few points
per fold to fit anything. Leave-one-out is the maximal use of data at
this sample size and is the standard fallback.

**Primary criterion: mean CRPS** (`scoringrules.crps_ensemble` against
each held-out year, using every candidate's Monte-Carlo sample — a
closed-form CRPS where available would differ negligibly at 5000
samples and using the ensemble estimator uniformly keeps every candidate,
including the two without a density, on the same footing).

**Log-likelihood is diagnostic only**, not the selection criterion, per
SPEC's "AIC as secondary only" — and this project goes further: AIC
itself is not computed at all (CRPS already does the model-complexity
tradeoff empirically, via held-out predictive skill, which AIC only
approximates asymptotically).

**Measured result (RAINCHNNAI, leave-one-out over all 31 seasons):**

| Candidate | mean CRPS | mean log-likelihood |
|---|---|---|
| kde_cv | 213.01 | -7.39 |
| gamma | 213.14 | -inf |
| weibull | 213.30 | -inf |
| kde_silverman | 213.57 | -7.37 |
| lognormal | 213.97 | -8.01 |
| bootstrap | 215.03 | n/a |
| enso_climatology | 231.03 | n/a |

**Selected: `kde_cv`**, by a narrow CRPS margin over gamma/weibull.

**The `-inf` log-likelihoods are a real, documented finding, not a
bug.** On at least one leave-one-out fold each, the unconstrained
3-parameter gamma and Weibull MLE fits placed `loc` such that the
held-out value fell outside the fitted distribution's support, giving it
zero density. This is a known instability of free-location MLE on small
samples (shape and loc partially trade off against each other) — and
it's direct empirical evidence for why SPEC specifies CRPS as the
primary criterion rather than log-likelihood/AIC: CRPS is bounded and
distance-based, so one unlucky fold doesn't make an otherwise-reasonable
candidate look infinitely bad.

**ENSO-conditioning underperforms** on this sample (CRPS 231.0, worst of
the seven) — plausible at n≈10 per tercile group: a within-tercile
sample that small adds more sampling noise than it removes from genuine
ENSO-conditional signal. Reported honestly rather than dropped, per
SPEC's "claims scale with sample size" principle — this is itself a
finding (ENSO-conditioning isn't yet pulling its weight at this sample
size), not a failure to hide.

## 4. What's written where

- `valuations` (method=`burn`, measure=`P`): burn mean/P5/P95, written
  for every currently-active RAINCHNNAI series.
- `valuations` (method=`dist`, measure=`P`): the selected candidate's
  Monte-Carlo mean/P5/P95, same series set.
- MLflow (`burn_distribution_selection` experiment): every candidate's
  CV scores, nested under one parent run per contract, naming the
  winner.

## 5. What's not done yet

- Detrending (none fit — see §1 above).
- A formal QQ/PIT diagnostic plot for the winning distribution (the
  numbers needed are all computed; just not plotted yet — `research/`
  scripts for this are future work, M15's "every paper figure comes from
  a script" requirement).
- Extending RAINCHNNAI's own LPA base period back to 1971 (currently
  using the 1991-2020 subset also used for RAINMUMBAI) would both
  enlarge n and let the burn/LPA computation use the contract's actual
  cited period rather than a 30-year window within it.
