# Methods note: forecasting ladder (M7)

**Milestone:** M7 (SPEC §7.6, F12). **Code:** `mq.forecasting.{features,climatology,analog,evaluate}`.

## What this answers

At an issue date `t` partway through a contract's season, what's a
reasonable probabilistic forecast of the *remaining* rainfall (and
hence the final CDR index)? SPEC specifies a model ladder, each rung a
separate `model_id` in the prediction ledger, evaluated by walk-forward
backtesting (train on strictly earlier seasons, test on the next one —
never split a season across folds, never look at a season's own future).

## 1. Training-row table (`mq.forecasting.features`)

One row per (year, issue_date) for every day of every historical
season: `observed_to_date_anomaly_mm` (the CDR deviation already
accumulated that season), `oni`, `dmi` (MJO omitted — still
bot-gate-blocked, same decision as M5.1/M6), `days_remaining`, and the
target `target_remaining_rain_mm` (raw remaining rainfall through
period_end — the same quantity `clim_v1`, SPEC's already-ledger-live
Week-1 rung, forecasts, so every later rung stays on a comparable scale
for CRPSS).

Built on the real 2-station averaged daily series (mirrors
`mq.index.engine`'s own station averaging) rather than clim_v1's
original single-station lookup — `clim_v1`'s existing ledger rows are
left untouched (SPEC: never modify ledger rows without asking); this
table is what every *new* rung, including a climatology baseline
recomputed consistently with them, trains on.

**Real run**: 3,751 rows across 31 historical seasons (1991-2020+2023).
The first implementation called `compute_index` once per issue-day
(~3,800 calls) and didn't finish in 2 minutes — rewritten as one
vectorized cumulative-sum pass per season; the real run now completes
in a few seconds.

## 2. The ladder's rungs

| Model | Idea | Status |
|---|---|---|
| `clim_v1` | Empirical climatology, single station | Ledger-live since M1 |
| `enso_clim_v1` | Climatology conditioned on ONI tercile | Built, backtested |
| `analog_v1` | k-nearest past seasons (k=5) on (anomaly, ONI, DMI) | Built, backtested |
| `lgbm_q_v1` / `lgbm_q_cqr_v1` | LightGBM quantile regression + conformal calibration | Not started — needs a new dependency decision |
| `tft_v1` (P2) | Temporal Fusion Transformer | Not attempted — see §4 |

`enso_clim_v1` reuses `mq.pricing.distribution.oni_terciles` (the same
within-sample tercile classification M4 built for burn-sample pricing).
`analog_v1` standardizes (anomaly, ONI, DMI) using only the *other*
years' same-issue-day rows and takes the k=5 nearest by Euclidean
distance — no new dependency; k-NN over 3 features and a few thousand
rows doesn't need scikit-learn.

## 3. Walk-forward backtest — real results, reported honestly

`mq.forecasting.evaluate.walk_forward_backtest` enforces "train <= year
y-1, test y": for each test year (once at least 10 strictly-earlier
years exist), builds a table of only prior years plus the single target
row, and calls the model on that. Real run, RAINCHNNAI, all 31 seasons,
`min_train_years=10`, n=2,541 predictions per model:

| Model | mean CRPS | CRPSS vs climatology | 50% coverage | 90% coverage |
|---|---|---|---|---|
| climatology baseline | 156.44 | — | 0.496 | 0.844 |
| `enso_clim_v1` | 165.44 | **-0.058** | 0.422 | 0.747 |
| `analog_v1` | 182.27 | **-0.165** | 0.319 | 0.609 |

**Both newer rungs underperform plain climatology at this sample size**
— SPEC's acceptance bullet is explicit that CRPSS gets reported
"whatever the sign," and this is the honest sign. This is not treated
as a bug to chase away by retuning `k` or the tercile cutoff against
this same backtest — doing that would just be overfitting the
hyperparameter to the one dataset being used to judge it, the opposite
of what walk-forward validation is for. It mirrors M4's own finding
that ENSO-conditioned climatology underperformed `kde_cv` for
burn/distribution pricing (CRPS 231.0 vs 213.01) — the same
sample-size-driven conclusion recurring at the forecasting-ladder level:
with only ~29-30 analog years available per issue-day, conditioning on
ONI tercile or taking a k=5 neighborhood both shrink the effective
sample further, and the resulting loss of averaging outweighs whatever
genuine ENSO/analog signal exists at n≈30 seasons.

`analog_v1`'s coverage is also notably too narrow (31.9% actual vs. 50%
nominal; 60.9% vs. 90% nominal) — a known general property of small-k
k-NN: the k nearest neighbors' own spread tends to underestimate the
true conditional uncertainty, especially when some of the k points
cluster close together. Not something this pass tries to patch with an
ad hoc variance inflation that wasn't independently validated — flagged
honestly instead.

Script + full output: `.scratch/forecasting_backtest.py` /
`.scratch/forecasting_backtest.log` (gitignored, real-data-dependent,
same pattern as the other real-data demo scripts this project has used).

## 4. What's not done yet

- **`lgbm_q_v1` / `lgbm_q_cqr_v1`**: need LightGBM, a new dependency —
  size/decision not yet checked against CLAUDE.md's ">50MB deps"
  threshold.
- **`tft_v1` (P2)**: not attempted. SPEC itself flags this as a weak
  candidate at "≈120 seasons" and asks for documented reasoning if
  skipped — this project's real sample is n=31, well below even that
  already-weak threshold, so a Temporal Fusion Transformer (which wants
  thousands of sequences to fit meaningfully) would almost certainly
  just overfit. Skipped with this reasoning on record, not silently.
- **Live ledger rows for `enso_clim_v1`/`analog_v1`**: `clim_v1` already
  writes daily ledger rows (M1); the newer rungs don't yet. Writing a
  live row needs the *current, in-progress* 2026 season's features,
  which `build_training_rows` can't produce as-is (it requires a
  complete historical season) — a separate "live row" builder is needed
  for the active season, not yet built.
- Research outputs SPEC also asks for at this milestone (reliability
  diagrams/PIT histograms plotted, not just the underlying values
  computed) are future `research/`-script work (M15's "every paper
  figure comes from a script" requirement), not blocked on anything.
