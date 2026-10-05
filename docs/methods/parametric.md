# Methods note: parametric cover designer (M11, part 1)

**Milestone:** M11 (SPEC §7.11, F17). **Code:** `mq.risk.parametric`.

## What this answers

A parametric cover pays out based on the *index*, not a buyer's actual
loss — simple and fast to settle, but it can fail exactly when the
buyer needed it (the index didn't trigger even though their local loss
was real). This module designs `(trigger, slope, limit)` to minimize
that "basis-failure probability" subject to a premium budget.

## 1. Built on what M4/M6/M9/M10 already provide

```
payout = min(limit, slope * max(0, I - trigger))   (wet cover)
payout = min(limit, slope * max(0, trigger - I))   (dry cover)
premium = E_Q[payout] * (1 + loading)
```

The Q-measure expectation is `mq.mpr.wang.wang_price` applied directly
to the payout array — the Wang transform doesn't care that it's a
capped/floored function of the index rather than the raw index. The
loss model reuses `mq.risk.hedge`'s `PiecewiseLinearExposure`
templates. The joint (loss, index) scenario shape is exactly what
`mq.risk.basis.local_index_series` already produces.

## 2. A real finding about the optimization objective itself

SPEC's stated objective — minimize `P(loss > threshold AND payout ==
0)` subject to `premium <= budget` — doesn't by itself reward being
*selectively* well-calibrated to real loss events over simply
triggering almost unconditionally. Running the real optimizer with a
trigger grid spanning the index's full historical range (including its
minimum) found exactly that: `trigger` at the index's lowest observed
value, firing in 30 of 31 years, driving basis-failure probability to
*exactly* 0 — not because the cover tracked loss events well, but
because it paid out (a tiny amount) almost every year regardless.
Mathematically a correct optimum of the stated objective; not a useful
design in practice. **Fixed by restricting the trigger grid to values
above the index's own historical median** (a parametric trigger that
fires on "wetter than typical" seasons, which is what a real cover
designer would choose anyway) — not a code fix, since the
near-unconditional solution is a legitimate optimum of SPEC's literal
objective given an unconstrained trigger range; restricting the search
space is the designer's judgment call, and SPEC doesn't specify where
that range should start.

A related, smaller note: when multiple `(slope, limit)` combinations
tie on basis-failure probability, the grid search keeps whichever is
evaluated first (ascending order in this module's own grids) rather
than applying an explicit secondary objective like "minimize premium
among ties." In practice this means ties resolve toward the cheapest
option, since the grids are defined ascending — convenient, but
incidental rather than a deliberate tie-break rule.

## 3. Real case study (SPEC's own stated one: synthetic Chennai delivery-rider exposure)

**Labelled synthetic per SPEC's own instruction** — the exposure model
itself is illustrative, same posture as M9's hedge-optimiser demo. Real
local rainfall (M10's weakest-correlation cell, 13.50°N 79.75°E) run
through `delivery_rider_income_loss`, paired against the real official
RAINCHNNAI index (M4), loss threshold at the empirical 75th percentile,
illustrative premium budget 50,000, `lam=0.0` (no real settlement data
to calibrate a real λ against — same bhavcopy blocker as M6/M8/M9),
`loading=0.2`:

| | no cover | optimized wet cover |
|---|---|---|
| trigger / slope / limit | — | 843.4 / 1.0 / 10,000 |
| P(loss > threshold) | **0.258** | **0.032** |
| premium | 0 | 200.1 (of 50,000 budget) |
| years paying out | — | 15 / 31 |

A real, substantial reduction in basis-failure probability (25.8% →
3.2%) for a tiny premium — the cover triggers selectively (15 of 31
years, roughly matching how often the index runs wetter than its own
median) rather than the degenerate near-always-pay solution §2
describes.

Script + full output: `.scratch/parametric_demo.py` /
`.scratch/parametric_demo.log` (gitignored, real-data-dependent, same
pattern as other real-data demos).

## 4. What's not done yet

- A real λ for the Q-measure premium — illustrative `lam=0.0` used
  throughout, same bhavcopy blocker as M6/M8/M9.
- An explicit secondary tie-break objective (e.g., minimize premium
  among basis-failure-probability ties) rather than relying on grid
  iteration order.
- Discounting (`discount_factor` parameter exists in `premium()` but
  wasn't exercised in this demo — no real discount curve to apply yet).
