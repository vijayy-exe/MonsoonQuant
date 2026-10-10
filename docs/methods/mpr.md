# Methods note: market price of risk (M6)

**Milestone:** M6 (SPEC §7.5, F11). **Code:** `mq.mpr.{wang,esscher,calibrate,uncertainty}`.

## What this answers

Given a P-measure payoff sample (the real M4 burn sample, or a fitted
distribution's Monte Carlo draws) and an observed market settlement
price, what risk-neutral (Q-measure) distortion would make the P-sample
price to that settlement — and how much should that distortion (λ or θ)
actually be trusted, given it's estimated from a single thin season's
worth of data?

Two independent transforms, per SPEC's own prescription:

1. **Wang transform**: `F*(x) = Φ(Φ⁻¹(F(x)) - λ)`, reweighting the
   P-sample's order statistics directly (no re-simulation).
2. **Esscher transform**: `dQ/dP ∝ exp(θ·z)`, a self-normalized
   importance-sampling exponential tilt.

## 1. Wang transform (`mq.mpr.wang`)

Implemented exactly on the sample's order statistics: sort the payoff
sample, assign each the plotting-position empirical CDF `i/(n+1)` (not
`i/n` — that would put the largest value at `F=1` exactly, where
`Φ⁻¹(1)=+inf` breaks the transform), map through
`F*(x) = Φ(Φ⁻¹(F(x)) - λ)`, and take the resulting CDF's increments as
Q-measure probability weights on the same order statistics.

**Sign convention, verified by test rather than assumed from a single
paper's stated direction** (Wang-transform literature states this both
ways depending on whether a given source applies it to the CDF or the
survival function — SPEC states it on the CDF `F` directly, so that's
exactly what's implemented): λ>0 makes `F*(x) < F(x)` everywhere, so `Q`
is stochastically larger than `P`, and `E_Q[payoff] > E_P[payoff]`. A
positive λ is a risk *loading* that raises the price above the physical
mean — confirmed numerically (`tests/unit/test_mpr_wang.py`), not just
derived on paper.

## 2. Esscher transform (`mq.mpr.esscher`)

Tilts on the **standardized** payoff `z = (x - mean(x)) / sd(x)`, not
raw payoff values. Raw CDR payoffs run ~300-2000mm; `exp(θ·x)` for any
θ near 1 overflows a double instantly, which would force θ into a
vanishingly small, uninterpretable range to avoid `inf`. Standardizing
first is a reparameterization, not a different transform —
`exp(θ·z) ∝ exp((θ/sd)·x)` as an importance weight, so Esscher-on-z
with parameter θ is textbook Esscher-on-x with `θ_raw = θ/sd`. This
puts θ on the same O(1), dimensionless scale as Wang's λ, so SPEC's
single "λ bounded in [-3, 3]" calibration bound applies to both
transforms without any contract-specific rescaling.

**Effective sample size (ESS)**, Kish's formula
(`1 / Σw_i²` for self-normalized weights): SPEC's own stated gate —
refuse the price outright (`LowEffectiveSampleSizeError`) when
ESS < 1% of N, rather than silently reporting a number dominated by a
handful of extreme-weight samples.

## 3. Calibration (`mq.mpr.calibrate`)

Both transforms calibrate the same way: Brent's method solves
`price_Q(param) = settle` for λ or θ, bounded to `[-3, 3]`. A settle
price unreachable within that bound (both endpoints give a gap of the
same sign) reports the nearer corner with `converged=False` rather than
raising — a corner solution is itself informative (the market is pricing
more risk-loading than this bound allows for), not a bug to hide.

Round-trip tests confirm both solvers recover a *known* generating
λ/θ exactly (construct `settle = price_Q(true_param)`, then calibrate
and check the recovered parameter matches) — the same discipline used
for the GLM coefficient-recovery tests in M5.1.

## 4. Uncertainty (`mq.mpr.uncertainty`)

Three distinct sources, reported separately per SPEC — collapsing them
into one number would hide which part of the estimate is trustworthy:

- **(a) Parametric bootstrap over P-model parameters**: resample the
  underlying years with replacement, recalibrate each time. Generic
  over "the resampled years *are* the payoff sample" (burn) and
  "resample years, refit the distribution, redraw its Monte Carlo
  sample" (a fitted-distribution candidate) via a caller-supplied
  `payoffs_from_years` function.
- **(b) Monte Carlo error**: closed-form delta-method standard error —
  the price estimate's own standard error (from the weighted sample's
  effective size) divided by the local slope `dprice/dparam` (central
  difference). Answers "how much noise does a finite sample add, even
  if the P-model were exactly right?" — a different question from (a).
- **(c) Bayesian pooled estimate across dates**: the SPEC headline
  number — conjugate normal-normal pooling of several dates' calibrated
  λ/θ, each with its own standard error and liquidity (trading-volume)
  weight, against a weak N(0,1) prior. Fully generic and tested without
  real market data (`tests/unit/test_mpr_uncertainty.py`) — the
  real-data application (pooling actual NCDEX settlement dates) is
  blocked on the same bot-gated bhavcopy feed as M2, documented in
  STATUS.md, not worked around.

## 5. Illustrative end-to-end run (real P-side data, hypothetical settle)

**There is no real NCDEX settlement price or volume data yet** —
bhavcopy fetch is bot-gated (same blocker as M2). The run below uses the
real M4 burn sample (n=31, mean=905.6mm, sd=388.5mm) and real
kde_cv-selected distribution, with the *settle* price chosen
illustratively to exercise the pipeline — **not a market observation,
and not a claim about the real rainfall risk premium** (SPEC §16's
language rule: "early empirical estimate", never a definitive number).
Script: `.scratch/mpr_demo.py` (gitignored — not a committed test, same
pattern as the other real-data demo scripts this project has used).

| Hypothetical settle | Wang λ | Esscher θ |
|---|---|---|
| 905.6mm (= P-mean) | 0.000 | 0.000 |
| 1000.0mm | 0.282 | 0.221 |
| 700.0mm | -0.658 | -0.779 |

Sanity-confirms both directions at once: settle = the P-mean recovers
λ=θ=0 exactly (no risk loading needed to match the physical mean);
settle above/below the mean recovers positive/negative parameters, as
the sign-convention derivation in §1 predicts.

Full uncertainty pipeline at the illustrative settle=1000.0mm:

| Source | Value |
|---|---|
| Calibrated λ | 0.2825 |
| (b) MC standard error | 0.2247 |
| (a) Bootstrap median [90% band] | 0.2956 [-0.042, 0.831] |
| (c) Illustrative 3-date Bayesian pool, mean [90% band] | 0.2559 [0.027, 0.485] |

The bootstrap band is wide — n=31 historical seasons is thin for this
kind of parameter, and the band says so honestly rather than
overstating precision. (c)'s 3 "dates" are themselves illustrative
(hypothetical volumes, not real trades) purely to demonstrate the
pooling mechanism works and narrows the band relative to a single
estimate, as more (even synthetic) observations should.

## 6. Real calibration (2026-10-11) — the bhavcopy blocker closed, for real

The bot-gate on ncdex.com's `/api/bhavcopy` backend is still real and
still not worked around (§0's own stance, unchanged). What changed:
the user manually downloaded two real UDiFF bhavcopy CSVs through the
website — the only ever-intended path (`mq run bhavcopy <csv>`, the
CLI wrapper added for exactly this handoff) — covering RAINCHNNAI's 3
listed series on 2026-10-05 and 2026-10-06. **First real,
non-illustrative calibration this project has ever run.**

| series | trade date | days to expiry | real settle (mm) | volume | OI |
|---|---|---|---|---|---|
| RAINCHNNAI-OCT26 | 2026-10-05 | 26 | 915.0 | 0 | 0 |
| RAINCHNNAI-OCT26 | 2026-10-06 | 25 | 912.0 | 0 | 0 |
| RAINCHNNAI-NOV26 | 2026-10-05 | 57 | 920.0 | 0 | 0 |
| RAINCHNNAI-NOV26 | 2026-10-06 | 56 | 916.0 | 0 | 0 |
| RAINCHNNAI-DEC26 | 2026-10-05 | 88 | 924.0 | 0 | 0 |
| RAINCHNNAI-DEC26 | 2026-10-06 | 87 | 920.0 | 0 | 0 |

**Every single real settlement observed so far has zero trading
volume and zero open interest** — NCDEX publishes a daily settlement
price for these contracts regardless, but nobody has actually traded
either RAINCHNNAI series yet. This directly answers VERIFY V11 ("are
these products actively trading") for real, for the first time: as of
this writing, no. Per SPEC §7.5's own instruction ("exclude zero-volume
days from headline λ... report them separately"), **every number below
is a zero-volume calibration, not a headline market price of risk.**

Calibrated against the real M4 burn sample (n=31, mean=905.6mm),
all 12 (series × date × transform) combinations converged cleanly —
no corner solutions, nowhere near the [-3, 3] bound:

| series | date | Wang λ [90% boot CI] | Esscher θ [90% boot CI] |
|---|---|---|---|
| OCT26 | 10-05 | 0.0284 [-0.323, 0.493] | 0.0246 [-0.321, 0.370] |
| OCT26 | 10-06 | 0.0193 [-0.332, 0.482] | 0.0168 [-0.330, 0.360] |
| NOV26 | 10-05 | 0.0434 [-0.306, 0.511] | 0.0374 [-0.306, 0.378] |
| NOV26 | 10-06 | 0.0314 [-0.320, 0.497] | 0.0272 [-0.318, 0.372] |
| DEC26 | 10-05 | 0.0555 [-0.293, 0.525] | 0.0476 [-0.290, 0.389] |
| DEC26 | 10-06 | 0.0434 [-0.306, 0.511] | 0.0374 [-0.306, 0.378] |

Wang and Esscher agree closely at every point (the Wang-vs-Esscher
consistency check SPEC §7.5 asks for) — both small, positive (a mild
risk loading above the physical mean, consistent with the real settle
prices sitting slightly above the 905.6mm P-mean). The bootstrap bands
are wide, same honest finding as §5's illustrative run: n=31 historical
seasons is thin, and two real dates is nowhere near enough for a
meaningful Bayesian pool across dates yet (that still needs more real
trading days — the same blocker as the research outputs below, now
narrowed to "need more days," not "need any real data at all").

The real risk-neutral (Q) prices themselves (`mq.pricing.writer.
write_q_measure_valuation`, `measure="Q_wang"`/`"Q_esscher"`) are also
written to `valuations` and live on `/v1/series/{id}/valuations/compare`
and the Pricing/Risk dashboard pages — by construction, `Q_wang`'s
fair_value reproduces the calibration settle exactly (912.0mm for
OCT26 10-06, etc.), which is the correct sanity check, not a
coincidence.

**Two real bugs this surfaced, fixed, not just worked around**:
1. The real bhavcopy CSV's own column header is `FininstrmActlXpryDt`
   (lowercase i in "nstrm"), not `FinInstrmActlXpryDt` as the
   registered schema spec states — a real NCDEX-vs-documentation
   discrepancy. Harmless to parsing (the column isn't used downstream),
   but `BHAVCOPY_SCHEMA` now matches the real file, not the written
   spec, with a comment explaining why.
2. The dashboard's Risk-page λ chart plotted every `mpr_estimates`
   point (Wang and Esscher both) on one undifferentiated line —
   invisible with only illustrative data, but with two real transforms
   sharing the same real as_of_date, it silently zigzagged between
   lambda and theta at every point. Fixed: Wang is the primary series
   (with its own CI band), Esscher overlays as a labeled dashed
   secondary — the same pattern already used for the Forecast page's
   observed-to-date line, and a real, visible rendering of SPEC's own
   named Wang-vs-Esscher consistency check instead of a hidden one.

## 7. What's still not done

- A real Bayesian pool across dates (needs more than 2 real trading
  days — the machinery is built and tested, §4).
- λ vs. days-to-expiry / λ vs. volume research plots — same "need more
  real dates" blocker, now narrowed from "need any real data."
- RAINMUMBAI has no real settlement data yet (no bhavcopy row for it
  has been downloaded) — its M4 burn/distribution pricing is real
  (see `docs/PROGRESS.md`'s 2026-10-11 entry), its Q-measure isn't.
