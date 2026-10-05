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

## 6. What's not done yet

- Real calibration against actual NCDEX settlement prices and volumes —
  blocked on the bhavcopy bot-gate (same root cause as M2), not a code
  gap.
- Research outputs SPEC asks for (λ vs. days-to-expiry, λ vs. volume,
  Wang-vs-Esscher consistency) need multiple real calibrated dates to
  plot against — same blocker.
