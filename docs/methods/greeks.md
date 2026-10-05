# Methods note: model sensitivities / Greeks (M9, part 1)

**Milestone:** M9 (SPEC §7.8, part of F14). **Code:** `mq.risk.greeks`.

**Label, up front, per SPEC**: these are *model sensitivities*, not
exchange-standard Greeks. No options market exists for this product;
there is no implied-vol surface or market-calibrated analogue to check
these against. They answer "how does this project's own simulator-based
fair value move when you bump an input," nothing more.

## 1. The four quantities

```
delta = [V(obs+dr) - V(obs-dr)] / (2*dr)      dr = 10mm, configurable
gamma = [V(obs+dr) - 2*V(obs) + V(obs-dr)] / dr**2
theta = V(t+1 | no-rain day) - V(t)   and   V(t+1 | climatological day) - V(t)
```

`V` is `mq.risk.greeks.full_season_payoff`'s mean: a direct call into
the M5 simulator (the C++ core, `mq.pricing.simulator`, not the NumPy
reference — see §3) for the full remaining season from a given
`(observed_to_date, start_date)`.

## 2. Common random numbers (CRN) — exact for delta/gamma, partial for theta

SPEC requires CRN because two *independent* Monte Carlo estimates of
`V` differ by noise that swamps a genuinely small sensitivity.

`observed_to_date` is a pure additive offset on `terminal_index` in
both simulator backends — it never touches any RNG draw. So bumping it
and reusing one seed gives **exact** path-for-path pairing: `V(obs+dr)`
and `V(obs-dr)` share identical per-path noise, and only the
deterministic shift differs. Delta and gamma get this for free.

Theta's two bumped valuations instead shift `start_date` by a day,
which *does* change which calendar day lands at RNG day-index 0 for the
bumped run. The season-level overdispersion multiplier is still shared
(it depends only on `(seed, path_id)`, not day index), but the
day-by-day draws are not identically paired. Every `GreekResult` reports
`pairing="exact"` or `pairing="partial"` rather than claiming the same
guarantee uniformly.

## 3. Why the C++ core here, not the NumPy reference

M8's `conditioned.py` uses the NumPy reference (`simulator_ref`) — one
simulate call per horizon, no tight precision requirement. Greeks are
different: theta's partial pairing needs many more paths to reach a
usable SE, and finding that out required actually computing it (§4),
not assuming it. Switched `full_season_payoff` to the C++ core
(`mq.pricing.simulator`) specifically because 1,000,000-path calls
taking ~1.7s each (vs. what would be minutes in NumPy) are what make
that path count practical at all.

## 4. Real results, RAINCHNNAI, 2026-10-03 (observed_to_date=815.3mm)

At n_paths=20,000 (chosen as a first, unexamined default):

| Greek | value | se | se_fraction | pairing |
|---|---|---|---|---|
| delta | 1.0000 | 0.0000 | 0.0000 | exact |
| gamma | -0.000000 | 0.000000 | 0.849 (see note) | exact |
| theta (no-rain day) | -10.410mm | 3.878 | **0.373** | partial |
| theta (climatological day) | 2.610mm | 3.863 | **1.480** | partial |

**Delta=1.0 and gamma=0.0 exactly are structural facts about the CDR
index, not numerical approximations that happened to land clean.** The
CDR index's own definition (SPEC §7.2: `spot(d) = spot(d-1) +
deviation(d)`) is additive in `observed_to_date` — the simulator never
makes the future distribution depend on where it started, only adds to
it. So `V` is *exactly* linear in `obs` with slope 1, for any fitted
chain model, any contract, any `n_paths`. Delta/gamma trivially satisfy
SPEC's SE<5% bar for this reason, not because CRN did a lot of work —
`gamma`'s own `se_fraction` (0.849) is a near-zero-divided-by-near-zero
artifact (both value and se round to ~1e-16), not a real 85%-of-value
uncertainty; reported for completeness, not as a finding.

Theta genuinely misses the bar at n_paths=20,000. Re-run at
n_paths=1,000,000 (practical only with the C++ core):

| Greek | value | se | se_fraction | pairing |
|---|---|---|---|---|
| theta (no-rain day) | -11.840mm | 0.538 | **0.0455** | partial |
| theta (climatological day) | -0.676mm | 0.539 | **0.798** | partial |

`theta_no_rain_day` now meets SPEC's bar (4.55% < 5%) — confirms the
partial-pairing hypothesis: more paths genuinely close the gap, it just
needed the C++ core's speed to be practical at this precision.

`theta_climatological_day` still misses badly (80%), and **this is not
a remaining bug** — it's a property of what the quantity measures. A
climatological day's deviation is `rain - LPA = 0` by definition, so
assuming tomorrow is climatological removes a zero-mean day from the
simulation. An unbiased model's *true* `theta_climatological_day` is
therefore plausibly exactly zero — it isolates pure variance reduction
(one fewer day of uncertainty) from any shift in the mean, and there
shouldn't be a mean shift. When the true value is zero, `se/value`
diverges regardless of sample size — a relative-SE threshold is
mathematically the wrong lens for this specific quantity, not a target
to keep chasing with more paths. (An absolute SE threshold, or a
formal zero-mean hypothesis test, would be the right tool here instead
— not implemented, since SPEC's own acceptance bar is stated as
relative.)

Script + full output: `.scratch/greeks_demo.py` / `.scratch/greeks_demo.log`
(gitignored, real-data-dependent, same pattern as the other real-data
demo scripts this project has used).

## 5. What's not done yet

- `delta`/`gamma` with respect to inputs *other* than `observed_to_date`
  (e.g. a covariate bump) — SPEC's formula is stated specifically in
  terms of `obs`, so not attempted; would need its own CRN analysis
  since covariates feed the GLM predictions, not an additive offset.
- An absolute-SE or hypothesis-test acceptance criterion for
  `theta_climatological_day` specifically, given its plausibly-zero
  true value makes the relative-SE bar structurally inapplicable.
