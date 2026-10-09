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

## 4. Re-derived for M15's `mq research reproduce` (2026-10-10) — a real discrepancy found, not papered over

Re-running this exact case study (same location, same plain-default
`delivery_rider_income_loss`, same P75 threshold choice) via the new,
committed `mq.research.reproduce.reproduce_parametric_case_study`
reproduces the optimized `trigger/slope/limit/premium/payout-years`
**exactly** (843.4 / 1.0 / 10,000 / 200.1 / 15-of-31) — confirmed both
directly and by calling the live `/v1/parametric/design` endpoint with
identical inputs. But the **basis-failure-probability figure itself
reproduces as 0.0 for both no-cover and optimized**, not the **0.258 ->
0.032** stated in §3's table above.

Root cause, found by inspecting the real loss array directly: ~84% of
this location's 31 real years saturate at exactly `max_loss` under
the exposure template's default `saturation_mm=200` (the local index's
real deviation range at this cell runs well past 200mm in most
years). The P75 threshold itself therefore lands on that same
saturated value, and `mq.risk.parametric.basis_failure_probability`'s
strict `>` comparison never counts a tied value as "exceeding" its
own threshold — a genuine edge case in the metric at this exposure
scale, not a transcription error in this note, and not something
fixed here (changing a strict inequality in an already-tested,
API-serving module deserves its own dedicated look, not a drive-by
edit while regenerating paper figures). The qualitative finding this
case study is built to illustrate — a well-chosen trigger range
produces a *selective* cover (15 of 31 years, roughly the wetter half)
rather than the degenerate near-always-pay solution §2 describes —
still holds; only the specific 0.258/0.032 numbers don't currently
reproduce. Reported honestly rather than silently reconciled — see the
preprint's own limitations section (§8).

## 5. What's not done yet

- A real λ for the Q-measure premium — illustrative `lam=0.0` used
  throughout, same bhavcopy blocker as M6/M8/M9.
- An explicit secondary tie-break objective (e.g., minimize premium
  among basis-failure-probability ties) rather than relying on grid
  iteration order.
- Discounting (`discount_factor` parameter exists in `premium()` but
  wasn't exercised in this demo — no real discount curve to apply yet).
