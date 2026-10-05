# Methods note: scenario lab (M11, part 2)

**Milestone:** M11 (SPEC §7.12, F18). **Code:** `mq.risk.scenarios`.

## What this answers

"What if ENSO/IOD conditions were different, or a cloudburst hit
tomorrow?" — this module answers that by perturbing model inputs and
re-running the already-built pricing/Greeks/hedge pipeline, **not** by
adding any new pricing math. It's pure orchestration over M5 (the
simulator), M9 (Greeks, hedge positions).

## 1. Grounding each preset honestly

- **ENSO/IOD presets** (El Niño, La Niña, neutral, positive/negative
  IOD): shock the ONI/DMI covariates the chain model's GLM (M5.1) was
  actually fit on — real values on the real scale, not placeholders.
- **"2015 Chennai floods analog"**: uses 2015's *real* ONI/DMI from the
  real ingested `climate_idx` data, not an illustrative shock — 2015 was
  a genuine strong El Niño year in this project's own M7 backtest
  record. The one preset that's historically grounded rather than
  approximate.
- **"Dry November"**: the chain model's seasonality comes entirely from
  Fourier harmonics of day-of-year — there's no month-specific dial to
  shock literally. Implemented as an explicitly-labelled illustrative
  dry-leaning ENSO/IOD shock rather than silently approximating
  something it structurally can't do exactly.
- **"+100mm cloudburst tomorrow"**: exact, not approximate — a direct
  `observed_to_date` bump using the identical additive-offset mechanism
  `mq.risk.greeks` already relies on for delta/gamma's exact CRN
  pairing.

## 2. Real run, all 8 scenarios, RAINCHNNAI, 2026-10-03

Real chain model, real LPA, real `observed_to_date`=815.3mm, an
existing -5-lot hedge position (M9's own real demo result) held
throughout to show its P&L sensitivity across scenarios:

| scenario | mean | P5 | P95 | delta | gamma | hedge P&L |
|---|---|---|---|---|---|---|
| El Niño (ONI=+2.0) | 752.2 | 317.4 | 1409.3 | 1.000 | ~0 | -188,060 |
| La Niña (ONI=-1.5) | 865.8 | 372.1 | 1611.0 | 1.000 | ~0 | -216,446 |
| Neutral ENSO | 815.5 | 348.7 | 1530.2 | 1.000 | ~0 | -203,885 |
| Positive IOD (+0.8) | 897.4 | 389.8 | 1662.1 | 1.000 | ~0 | -224,350 |
| Negative IOD (-0.8) | 730.1 | 305.1 | 1370.7 | 1.000 | ~0 | -182,535 |
| Dry November (illustrative) | 793.9 | 337.1 | 1485.8 | 1.000 | ~0 | -198,468 |
| Cloudburst (+100mm) | 913.0 | 447.5 | 1626.2 | 1.000 | ~0 | -228,247 |
| **2015 real analog** (ONI=+2.28) | 790.1 | 337.0 | 1473.3 | 1.000 | ~0 | -197,524 |

**Delta=1.0 and gamma≈0 across every single scenario** — the same
structural finding M9 made (the CDR index is additive in
`observed_to_date` by construction, so its sensitivity there is always
exactly 1 regardless of ENSO/IOD state), now confirmed under 8
different real covariate shocks, not just the baseline.

**The real 2015 analog (790.1mm) lands close to the synthetic
`el_nino` preset (752.2mm)** — both driven by a similarly strong
positive ONI (+2.28 real vs. +2.0 synthetic), a genuine
internal-consistency check: two independently-derived strong-El-Niño
inputs produce similar outputs, as they should if the model is doing
what it's supposed to. Cloudburst, as expected structurally, gives the
single highest mean (913.0mm — baseline + 100mm minus the bump day's
own LPA).

Script + full output: `.scratch/scenarios_demo.py` /
`.scratch/scenarios_demo.log` (gitignored, real-data-dependent, same
pattern as other real-data demos).

## 3. What's not done yet

- Valuations under burn/distribution methods (M4) and the
  forecast-conditioned pipeline (M8) specifically — this module
  currently reports only the simulator's own mean/P5/P95, not SPEC's
  full "valuations under all methods."
- A re-optimized hedge per scenario (vs. this run's fixed existing
  position's P&L) — `mq.risk.hedge`'s optimizer could be re-run per
  scenario, not wired in here.
- Dashboard-side scenario comparison UI (M13).
