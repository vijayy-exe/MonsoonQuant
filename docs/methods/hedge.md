# Methods note: hedge optimiser (M9, part 2)

**Milestone:** M9 (SPEC §7.9, F15). **Code:** `mq.risk.{hedge,cvar}`.

## What this answers

Given a rainfall exposure at some location (not necessarily one of the
real contract's two official stations) and the real contract index as
the hedging instrument, how many lots should you hold, and how much
risk does that actually remove? Two answers per SPEC: a min-variance
position, and a CVaR95-minimizing position (which can differ, since
minimizing variance and minimizing tail risk aren't the same
objective).

## 1. Sign convention — stated explicitly because two modules disagree on purpose

SPEC's own formula: `h* = -Cov(L,X)/Var(X)` for the position `L + h*X`.
`mq.risk.basis`'s `hedge_ratio` (M10) reports the *same*
minimum-variance decomposition for `L - h*X` instead (the standard
textbook regression-hedge framing). Both are correct for what they
report; `mq.risk.basis`'s `hedge_ratio` equals `-1 ×` this module's
`h_star` for the same `(L, X)` pair. Only `mq.risk.hedge`'s sign is
meant to be read as an actionable "go long/short" instruction — this is
documented in both modules' docstrings, not left to be discovered by
whoever reads them side by side.

## 2. Exposure templates

SPEC's four named templates (delivery-rider income loss, crop yield
loss, event cancellation, construction downtime) are all
`PiecewiseLinearExposure` presets — one generic breakpoints-based
building block covers all of them, since each is itself a
piecewise-linear function of local rainfall with a different
shape/sign. **Illustrative, not calibrated to a real business** — same
posture as SPEC's own labelled-synthetic §7.11 case study.

## 3. CVaR via `scipy.optimize.linprog`, not `cvxpy`

The Rockafellar-Uryasev LP is solved with `scipy.optimize.linprog`'s
HiGHS backend — the literal solver SPEC names ("cvxpy/HiGHS") — rather
than adding `cvxpy` as a new dependency. Integer lots via enumeration
over a small neighborhood of the continuous optimum (SPEC's own stated
alternative to a full MILP), evaluating exact empirical CVaR per
candidate directly on the scenarios.

## 4. A real structural finding, confirmed on real data

While testing `minimize_cvar_hedge`, an all-positive synthetic index
hit the unconstrained search's boundary rather than any interior
optimum — unlike variance (quadratic, always has an interior minimum),
CVaR minimization can be genuinely unbounded when the index's sign
never varies across scenarios: shorting ever more aggressively keeps
improving every scenario's loss without limit.

**Running the real optimizer against the real RAINCHNNAI index
confirmed this is not just a synthetic-test artifact.** The real
official burn sample (M4) is positive in every one of the 31 historical
seasons — RAINCHNNAI has never settled a season below its own
season-LPA anchor in this record. The unconstrained CVaR hedge for a
real candidate exposure genuinely wants to short without limit for
exactly the reason found in testing, and only hit a sensible answer
because `LotConstraints(max_order_lots=20)` was supplied. **For this
specific contract, position limits are not a risk-management nicety on
top of the CVaR optimizer — they're required for the optimization to
be well-posed at all**, given the real index's historical sign
behavior.

## 5. Real end-to-end run

Real official index (M4's burn sample), real local rainfall at a
candidate exposure location (13.50°N, 79.75°E — the weakest-correlation
cell from M10's real basis-grid run, correlation 0.734, hedge
effectiveness 0.538 as a raw basis-risk diagnostic), run through the
illustrative delivery-rider income-loss template
(`max_loss=500,000` — chosen only to land in a lots range worth
reporting, not a claim about any real business's actual scale),
`multiplier=50` (RAINCHNNAI's real INR-per-point value, used here
illustratively since there is still no real settlement/margin data —
same bhavcopy blocker as M2/M6/M8), `LotConstraints(max_order_lots=20,
margin_budget=100,000, margin_per_lot=2,000)`:

| | min-variance | CVaR95 |
|---|---|---|
| `h*` (continuous) | -242.22 | -1000.00 (hit the position-limit bound — see §4) |
| lots | -5 | -20 |
| hedge effectiveness / CVaR | 0.420 | cvar_95 = -310,007.6 |
| do-nothing comparison | sd 145,214 → 110,633 | CVaR95 500,000 → -310,007.6 |
| basis contribution | 0.999 (rounding to 5 whole lots costs almost nothing extra) | — |

A smaller illustrative exposure (`max_loss=5,000` or `50,000`) rounds
to **zero lots** for the min-variance hedge — not a bug, a real
position-sizing finding: a real futures contract's monetary multiplier
(50 INR/point, on an index that moves by hundreds of points across a
season) can be too coarse for a genuinely small exposure to hedge with
whole lots at all. The CVaR optimizer, by contrast, hits its position
*limit* boundary in every one of these exposure-scale variants,
regardless of exposure magnitude — confirming §4's finding is about the
index's own sign history, not an artifact of exposure scale.

Script + full output: `.scratch/hedge_demo.py` / `.scratch/hedge_demo.log`
(gitignored, real-data-dependent, same pattern as other real-data demos).

## 6. What's not done yet

- Real margin/notional figures — illustrative values used throughout,
  same bhavcopy blocker as M2/M6/M8.
- Basis contribution for the CVaR hedge specifically (only computed for
  the min-variance report currently).
- Scenario-lab integration (SPEC §7.12) and the dashboard-side hedge
  comparison UI (M13).
