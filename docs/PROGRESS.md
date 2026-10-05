# Progress Log

Running log, most recent first. Each entry: date, task ID, what changed,
measured numbers.

---

## 2026-10-05 (cont. 6) — M8 forecast-conditioned pricing: real end-to-end run confirms SPEC's own non-monotonic-uncertainty warning

Continuation of the same day, after M7 was closed out. User said
"continue until session limit hits"; picked up SPEC's M8
(forecast-conditioned pricing, `mq.pricing.conditioned`).

- **`quantile_map`**: rank-based CDF matching that remaps the
  simulator's (M5) near-term simulated totals onto a forecast's (M7)
  marginal distribution while preserving the simulator's path-for-path
  ordering — the mechanism that lets this module trust the forecast for
  the near term and the simulator's generative structure (spell
  lengths, calibrated seasonal variance) for the far term.
- **No simulator code changes needed for the near-term/remainder
  split** — a design insight worth recording: every RNG draw in both
  M5 simulator backends is a pure function of (seed, path_id,
  day_index), never of total n_days. Running `simulate()` twice with
  the same seed/start_date — once for n_days=h, once for the full
  remaining window — gives path-for-path identical first-h-day draws
  between the two calls, so subtracting isolates the remainder exactly.
  Verified via a law-of-large-numbers check, not just asserted.
- **`remaining_rain_climatology_2station`**: `clim_v1`'s 2-station,
  horizon-capped counterpart, used as the "forecast quantiles for next
  h days" source. Chose plain climatology deliberately (not
  `enso_clim_v1`/`analog_v1`/an LightGBM rung) because M7's own real
  backtest found it had the best CRPS of all 5 built rungs — a
  data-driven choice referencing this project's own prior real result,
  not an arbitrary default. `clim_v1`'s existing single-station
  function was left untouched (ledger-live).
- **Real end-to-end run**, real chain model, real LPA, real ONI/DMI,
  real observed_to_date=815.3mm (2026-10-03, from STATUS.md's live
  state): computed the 90% band width at h=7/14/30/60/89 days =
  1171.5/1175.1/1124.6/**1420.4**/1240.4mm. **Genuinely non-monotonic**
  — confirms SPEC's own explicit instruction ("never assume monotonic
  shrinking uncertainty; plot band width vs time and let data speak")
  on real data rather than leaving it as an untested caveat. The h=60
  spike has a plausible explanation (late-season NE monsoon rainfall is
  where ENSO-linked variability is largest for Chennai) flagged as
  plausible-not-verified, not overclaimed. Illustrative Wang λ computed
  at each h too (settle fixed at a hypothetical 950mm throughout, not a
  real trade — still no real settlement data, same bhavcopy blocker as
  M6). Script + log: `.scratch/conditioned_demo.py` (gitignored).
  Full write-up: `docs/methods/conditioned.md`.
- `docs/STATUS.md`, `CLAUDE.md` updated: M8 row and F13 now done, new
  M8 detail table, resume-pointer moved to M9 (Greeks + hedge
  optimiser, `mq.risk`).

---

## 2026-10-05 (cont. 5) — M7 forecasting ladder complete: lgbm_q_v1, lgbm_q_cqr_v1; all 5 rungs real-backtested

Continuation of the same day. User approved adding LightGBM (1.5MB
macOS wheel, core deps already present) after a size check; picked up
the two remaining forecasting-ladder rungs.

- **`lgbm_q_v1`** (`mq.forecasting.lgbm_quantile`): one LightGBM model
  per quantile level, monotone rearrangement to fix LightGBM's known
  quantile-crossing problem. **Had to switch APIs mid-build**: the
  sklearn-compatible `LGBMRegressor` wrapper turned out to
  hard-require scikit-learn at import time — an unplanned, much larger
  dependency the earlier size check never covered. Switched to
  lightgbm's native `Dataset`/`Booster` API, which needs only the
  lightgbm package itself.
- **`lgbm_q_cqr_v1`** (`mq.forecasting.conformal`): split-conformal
  calibration on top of `lgbm_q_v1`, aimed directly at the
  under-coverage problem `analog_v1` showed in the earlier backtest.
  Holds out a whole-season calibration fold, computes each quantile's
  signed residual on it, and shifts future predictions by the
  residuals' own empirical quantile — applied to every level in the
  grid, not just one interval's endpoints.
- **Promoted a "private" helper to public**: `conformal.py` needed
  `lgbm_quantile.py`'s inverse-CDF sampling function, which had a
  leading underscore. Renamed it public (`samples_from_quantile_grid`)
  rather than reach into another module's internals — a small but
  real code-quality fix caught before it shipped.
- **Real walk-forward backtest extended to all 5 built rungs.** Same
  honest pattern continues: `lgbm_q_v1` (CRPS=194.03, CRPSS=-0.240) and
  `lgbm_q_cqr_v1` (CRPS=201.92, CRPSS=-0.291) both underperform plain
  climatology too — every added-complexity rung does, at this sample
  size. **But the conformal layer's actual job — fixing coverage — is
  a real, measured success**: `lgbm_q_v1` under-covers badly
  (33.1%/68.6% vs. 50%/90% nominal, same pattern `analog_v1` showed);
  `lgbm_q_cqr_v1`'s calibrated coverage (45.5%/86.3%) lands much closer
  to nominal. Reported as two separate, both-true findings rather than
  picking one headline number: the mechanism works, it still isn't
  enough data to beat climatology on CRPS. Script + log:
  `.scratch/lgbm_backtest.py` (gitignored, real-data-dependent).
- `docs/STATUS.md`, `CLAUDE.md`, `docs/methods/forecasting.md` updated
  with the final 5-rung comparison table. **M7 is now fully complete.**
  Resume-pointer moved to M8 (forecast-conditioned pricing,
  `mq.pricing.conditioned`).

---

## 2026-10-05 (cont. 4) — M7 forecasting ladder: clim_v1 extended with enso_clim_v1, analog_v1; real walk-forward backtest

Continuation of the same day, after M6 was closed out. User said
"continue"; picked up SPEC's M7 (forecasting ladder, `mq.forecasting`).

- **`mq.forecasting.features.build_training_rows`**: one row per
  (year, issue_date) across every historical season — the shared
  training table `enso_clim_v1`, `analog_v1`, and later rungs all use.
  Built on the real 2-station averaged daily series (mirrors
  `mq.index.engine`'s own station averaging), not clim_v1's original
  single-station lookup — clim_v1's existing ledger rows are left
  untouched per SPEC's "never modify ledger rows without asking."
  **Real perf bug caught before it became a 2-minute-plus hang**: the
  first version called `compute_index` once per issue-day (~3,800
  calls for the real 31-season sample) and didn't finish inside a
  2-minute timeout — the same per-call LPA/grid-lookup cost M4's own
  burn-analysis perf fix addressed, just multiplied ~120x by one call
  per day instead of one per season. Rewrote the anomaly feature as a
  single vectorized cumulative-sum pass per season instead: real run
  now completes in a few seconds (3,751 rows, 31 years).
- **`enso_clim_v1`** (`mq.forecasting.climatology`): empirical
  quantiles of remaining rain from years sharing the target year's ONI
  tercile — reuses `mq.pricing.distribution.oni_terciles` directly
  (M4's own tercile classification, now serving a second milestone).
- **`analog_v1`** (`mq.forecasting.analog`): k=5 nearest past seasons
  by standardized Euclidean distance on (observed-to-date anomaly, ONI,
  DMI). No new dependency — k-NN over 3 features and a few thousand
  rows is a few lines of NumPy, not a reason to add scikit-learn.
- **`mq.forecasting.evaluate`**: CRPS (via `scoringrules`, already a
  dependency), CRPSS, pinball loss, interval coverage, PIT values, and
  a walk-forward backtest harness that enforces "train ≤ year y-1" by
  construction (each test row is forecast using a table built from only
  strictly-prior years plus that one row — the same shape the live
  forecast functions already expect, so backtesting and live forecasting
  share one code path).
- **Real walk-forward backtest, RAINCHNNAI, all 31 seasons,
  min_train_years=10, n=2,541 predictions per model — an honest
  negative finding, reported as such**: both `enso_clim_v1` (CRPSS=
  -0.058) and `analog_v1` (CRPSS=-0.165) underperform plain
  climatology. This was **not** retuned to chase a positive number —
  doing that against the same backtest used to judge it would just be
  overfitting the hyperparameter to this one dataset, exactly what
  walk-forward validation exists to prevent. It also isn't a surprise
  in isolation: it mirrors M4's own finding that ENSO-conditioned
  climatology underperformed `kde_cv` for burn pricing (CRPS 231.0 vs.
  213.01) — the same small-sample conclusion (n≈30 analog years per
  issue-day) recurring at the forecasting-ladder level. `analog_v1`'s
  coverage also runs narrow (31.9%/60.9% actual vs. 50%/90% nominal) —
  a known small-k k-NN property, reported rather than patched with an
  unvalidated variance-inflation hack. Full write-up:
  `docs/methods/forecasting.md`. Script + log:
  `.scratch/forecasting_backtest.py` (gitignored, real-data-dependent).
- **`tft_v1` (P2) deliberately skipped, reasoning on record**: SPEC
  itself flags this rung as a weak candidate at "≈120 seasons"; this
  project's real sample is n=31, well below even that already-weak
  threshold — a Temporal Fusion Transformer would almost certainly just
  overfit at this scale.
- **Not yet done**: the LightGBM rungs (`lgbm_q_v1`, `lgbm_q_cqr_v1`)
  need a new dependency decision (size check against CLAUDE.md's
  >50MB-without-asking rule, not yet done); live ledger rows for the
  two newer rungs need a separate "live row" builder for the
  in-progress 2026 season (`build_training_rows` requires a *complete*
  historical season, so it can't build today's own row as-is).
- `docs/STATUS.md`, `CLAUDE.md` updated: M7 row now in-progress with
  the real CRPSS numbers, new M7 detail table, F12 updated.

---

## 2026-10-05 (cont. 3) — M6 market price of risk: Wang + Esscher, calibration, uncertainty

Continuation of the same day, after M5 was closed out. User said
"proceed"; picked up SPEC's M6 (market price of risk, `mq.mpr`).

- **`mq.mpr.wang`**: Wang transform implemented by reweighting an
  existing P-measure sample's order statistics (no re-simulation, per
  SPEC) — plotting positions `i/(n+1)` rather than `i/n` to avoid the
  `Phi^-1(0)`/`Phi^-1(1)` singularities at the sample extremes. The
  sign convention (lambda>0 raises the price above the P-mean) was
  *verified by test*, not assumed from a single paper's stated
  direction — Wang-transform literature states it both ways depending
  on whether a source applies it to the CDF or survival function, and
  this derivation + test confirms SPEC's own CDF-based formula gives
  lambda>0 -> higher price.
- **`mq.mpr.esscher`**: tilts on the *standardized* payoff, not raw mm
  values — raw CDR payoffs run ~300-2000mm, and `exp(theta*x)` for any
  theta near 1 overflows a double instantly at that scale. Standardizing
  first is a reparameterization (not a different transform), and it
  puts theta on the same O(1) scale as Wang's lambda, so SPEC's single
  "bounded in [-3,3]" calibration bound applies to both without
  per-contract rescaling. SPEC's own "refuse below 1% ESS" gate raises
  `LowEffectiveSampleSizeError` rather than silently returning an
  unreliable self-normalized estimate.
- **`mq.mpr.calibrate`**: Brent-solves lambda/theta to match a settle
  price. Round-trip tests confirm both solvers recover a *known*
  generating lambda/theta exactly (construct settle from that same
  parameter, then calibrate and check it comes back out) — the same
  discipline used for the M5.1 GLM coefficient-recovery tests.
- **`mq.mpr.uncertainty`**: three distinct sources, per SPEC, kept
  separate rather than collapsed into one number: (a) bootstrap over
  resampled years (generic over "resampled years are the payoff sample"
  vs. "resample, refit, redraw"), (b) closed-form delta-method MC
  error, (c) Bayesian pooling across dates via conjugate normal-normal
  update with a weak N(0,1) prior and liquidity (volume) weighting —
  SPEC's headline number. All three built and tested without needing
  any real market data.
- **Illustrative end-to-end run against real M4 data** (real n=31 burn
  sample, real kde_cv-selected distribution) — settle price chosen
  illustratively since there is no real NCDEX settlement data yet
  (bhavcopy bot-gate, same as M2). Confirms the math from both ends:
  settle = the P-mean recovers lambda=theta=0 exactly; settle above/
  below the mean recovers the predicted sign. Full uncertainty pipeline
  at an illustrative settle=1000mm: bootstrap 90% band
  [-0.042, 0.831] (wide — n=31 is genuinely thin for this), illustrative
  3-date Bayesian pool [0.027, 0.485]. Script: `.scratch/mpr_demo.py`
  (gitignored, not a committed test, same pattern as other real-data
  demo scripts). Full write-up: `docs/methods/mpr.md`.
- `docs/STATUS.md` and `CLAUDE.md` updated: M6 row now in-progress
  (machinery done, real calibration blocked), F11 updated, new M6
  detail table, resume-pointer moved to M7 (forecasting ladder).

---

## 2026-10-05 (cont. 2) — M5.3 C++ core: pybind11 + OpenMP + Philox4x32-10; M5 complete

Continuation of the same day. User chose "build the C++ core now" when
asked how to proceed after M5.1/M5.2.

- **New `core/` package**: its own uv workspace member, scikit-build-core
  + pybind11 build backend — kept separate from the main hatchling-built
  `mq` package so installing `mq` for analysis-only use never requires a
  C++ compiler. `uv sync` builds and installs it automatically, same as
  any other dependency.
- **Philox4x32-10 implemented from scratch** (the published Salmon,
  Moraes, Dror, Shaw 2011 constants and round structure) rather than
  vendoring the full upstream Random123 header library — fetched the
  canonical `philox.h` from DEShawResearch/random123 via `gh api` purely
  to *verify* constants/structure, not to vendor it. **Verified
  bit-for-bit** against three of Random123's own published known-answer
  test vectors (all-zero, all-ones, and an asymmetric key/counter case)
  before trusting the header for anything else — exact match on all
  three.
- **OpenMP on Apple Clang needed an explicit fix**: `find_package(OpenMP)`
  silently fails on macOS because Apple Clang ships no OpenMP runtime of
  its own — a known CMake/macOS gotcha, not specific to this project.
  Fixed by pointing CMake at Homebrew's already-installed `libomp`
  explicitly in `core/CMakeLists.txt`. Caught by checking
  `core.OPENMP_ENABLED` after the first build (it was `False`) rather
  than assuming the flag had taken.
- **Marsaglia-Tsang Gamma sampling via Philox**, including the shape<1
  boost trick (`Gamma(a) = Gamma(a+1) * U^(1/a)`) — exercised with the
  real fitted shape (0.316, M5.1), not just a toy value. Every RNG draw
  (occurrence Bernoulli, Gamma rejection-loop retries, the season-level
  overdispersion multiplier) is a pure function of (key, path_id, day,
  stream_id, attempt) with zero shared mutable state.
- **Measured results**:
  - 1,000,000 paths × 92 days: **0.80s** (SPEC's budget is 10s — 12x
    margin). Logged to `docs/benchmarks/simulator_1m_paths.txt`.
  - Same seed → **bit-identical SHA-256 digest** across OMP_NUM_THREADS
    = 1, 2, 4, 8 (verified via subprocess, since OpenMP reads the env var
    once at its first parallel region).
  - C++ core vs. the M5.2 NumPy reference: statistical agreement within
    Monte Carlo noise on two synthetic degenerate models (including the
    shape<1 case) — different RNGs, same model, same distributional
    moments.
- **Refactor**: factored the per-day GLM-prediction + LPA-lookup step
  (duplicated the moment a second simulator backend existed) into
  `mq.pricing.simulator_features.build_daily_arrays`, and moved
  `DailyLPA`'s dict-building into `mq.index.lpa.daily_lpa_lookup` — both
  backends now share one implementation, can't silently drift apart.
- `mq.pricing.simulator` (production, C++-backed) added alongside the
  existing `mq.pricing.simulator_ref` (NumPy reference, kept per SPEC's
  own requirement for an independent cross-check).
- New `tests/statistical/`: parity, cross-thread determinism, and the
  `make bench` benchmark — all pass, all real measurements, none
  fabricated.
- `CLAUDE.md`'s "Current milestone" section was badly stale (still said
  M3 was next, from several sessions ago) — updated to reflect M0-M5
  complete, M6 next.
- **M5 is now fully complete** (M5.1, M5.2, M5.3). `docs/STATUS.md`
  updated throughout; "how to resume" now points at M6 (market price of
  risk).

---

## 2026-10-05 (cont.) — M5.1 GLM fitting + M5.2 NumPy reference simulator, overdispersion fix validated on real data

Continuation of the same day, after M4 was closed out. Picked up SPEC's
M5 (simulator) milestone.

- **Checked the C++ toolchain before deciding how to proceed**: cmake,
  Apple clang (C++20), and libomp are all *already installed* on this
  machine (confirmed via `cmake --version`, `clang --version`, `brew
  list libomp`) — no system-level installs needed for M5.3. Only
  pybind11 and scikit-build-core (small Python packages) remain to add
  when M5.3 starts.
- **M5.1** (`mq.pricing.simulator_glm`): logistic GLMs for the 2-state
  Markov occurrence chain (p01, p11) and a Gamma log-link GLM for
  wet-day amount, all on Fourier harmonics of day-of-year + ONI/DMI
  covariates (MJO still omitted, bot-gate-blocked). Hand-rolled MLE via
  `scipy.optimize` rather than adding statsmodels/sklearn — consistent
  with `mq.pricing.distribution`'s existing scipy-direct style, and
  these are small (<10-parameter) fits. **Real fit**, nungambakkam
  station, n=11,323 days (1991-2020+2023): both occurrence GLMs and the
  amount GLM converge; amount shape=0.316 (strongly right-skewed wet-day
  amounts — expected for rainfall).
- **M5.2** (`mq.pricing.simulator_ref`): NumPy reference chain-dependent
  simulator — day-by-day Markov occurrence + Gamma amount draw,
  accumulating (rain - LPA) deviation exactly the way
  `mq.index.engine.compute_index` does, so the simulator's output lands
  on the same CDR-spot scale as the real index.
- **Overdispersion fix implemented and validated against real data, not
  just coded**: SPEC flags that chain-dependent models
  "under-disperse seasonal totals" — rather than take that as given,
  measured it on the real 31-season single-station history first. A
  plain simulation (no fix) gives seasonal-total sd=272.5mm against a
  real historical sd=412.3mm — confirms the literature problem is real
  on this data, by about 34% too little spread. Added one lognormal
  multiplier per path on that path's whole-season amount-mean (a
  season-level random effect, per SPEC's own prescription), with
  `calibrate_overdispersion_sd()` root-finding (Brent) the multiplier's
  sd that reproduces a target seasonal-total sd. Calibrated value
  (sigma=0.336) gives simulated sd=418.5mm — within 2% of the 412.3mm
  target, comfortably inside SPEC's ±10% acceptance band. Script + full
  output saved to `.scratch/validate_simulator.py` /
  `.scratch/validate_simulator.log` (gitignored, real-data-dependent —
  same pattern as the existing backfill scripts, not a committed test).
- Unit tests for both modules use synthetic data: property-style
  coefficient-recovery tests for the GLMs, and degenerate
  always-wet/always-dry models for exact (non-statistical) simulator
  correctness checks, plus a same-seed determinism check and a
  law-of-large-numbers convergence check. All pass; `make check` green
  throughout.
- **What M5.3 (C++ core) will need, not yet started**: pybind11 +
  scikit-build-core wiring (new build-system integration, bigger than
  anything done so far this project), a from-scratch Philox4x32-10
  implementation (the published Salmon et al. 2011 constants directly,
  rather than vendoring the full upstream Random123 header tree — same
  algorithm, no new external fetch needed), OpenMP parallelism,
  determinism-across-thread-count tests, parity tests vs. the NumPy
  reference, and the `make bench` 1M-paths-in-under-10s benchmark.
  SPEC's own statistical holdout window is 1951-2020; the real backfill
  only reaches 1991-2020+2023 so far — extending it further back is a
  data task (same backfill script, more years), not a code task.
- `docs/STATUS.md` updated: M5 row now 🟨 (M5.1/M5.2 done, M5.3 not
  started), new M5 detail table with the real overdispersion numbers,
  "how to resume" now points at M5.3's specific remaining pieces.

---

## 2026-10-05 — M4.2 distribution selection (real results); M4 complete; LPA/grid-cell perf fix

- **M4.2 distribution fitting + selection, run for real against the full
  31-season RAINCHNNAI burn sample** (`mq.pricing.distribution`,
  `mq.pricing.selection`): 7 candidates (gamma, lognormal, weibull,
  kde_silverman, kde_cv, bootstrap, enso_climatology), scored by
  leave-one-out CV using mean CRPS (`scoringrules`) as the primary
  criterion, log-likelihood diagnostic only. **Selected: `kde_cv`**
  (CRPS=213.01), narrowly ahead of gamma (213.14) and weibull (213.30).
  fair_value=902.7mm, lo90=318.0mm, hi90=1796.6mm — written to
  `valuations` (method=dist, measure=P) for all 3 active RAINCHNNAI
  series. Full candidate scores logged to MLflow
  (`burn_distribution_selection` experiment).
- **Self-caught factual error, corrected before it propagated**: the
  methods note first claimed 2005 and 2015 (the two wettest burn years)
  were "both known strong El Niño years." Independently re-ran
  `season_oni()` against the real ingested ONI data before relying on
  this claim further: 2015's ASO-mean ONI is 2.01 (strong El Niño,
  confirmed), but 2005's is **-0.17** (near-neutral — not El Niño).
  Corrected `docs/methods/burn_distribution.md` immediately.
- **MLflow port-5000 403s root-caused**: not an MLflow auth issue —
  macOS's AirPlay Receiver (ControlCenter) owns port 5000 by default and
  403s anything Docker tries to forward there. `lsof -nP -iTCP:5000
  -sTCP:LISTEN` showed `ControlCenter` as the listener. Fixed by
  remapping MLflow to host port 5001 (`docker-compose.yml`,
  `mq.config.mlflow_tracking_uri`); verified with an actual successful
  `mlflow.start_run()` call, not just a port-open check.
- **Perf fix: `compute_index`'s LPA + grid-cell lookup, cached/reused
  across burn's 31 calls.** Two real bugs found by actually timing the
  full 31-season reconstruction after M4.2 (not caught by golden tests,
  which use tiny fixtures):
  1. Each station's ~50-year LPA groupby was recomputed from scratch on
     every one of burn's 31 `compute_index` calls, even though all 31
     share the identical LPA base period. Added an optional `lpa_cache:
     dict[(station_id, base_start, base_end), DailyLPA]`, threaded
     through `mq.pricing.burn.build_burn_sample` → `reconstruct_season` →
     `compute_index`, so each station's LPA is computed once total
     instead of once per year.
  2. Even with (1), `_station_daily_rainfall`'s own `nearest_cell` call
     was re-scanning the full multi-decade `rain_grid`'s distinct cells
     on every call — the *same* cell `compute_daily_lpa` had already
     resolved for that station. Reused the LPA's already-resolved
     `cell_lat`/`cell_lon` directly instead of a second lookup.
  - **Measured**: real 31-season `build_burn_sample` run, before/after:
    **254s → 12s (~21x)**. `BurnStats` output byte-identical before and
    after (verifies the optimization changed nothing observable, only
    cost). All 8 golden tests + full `make check` pass unchanged.
- **M4 is now complete**: both burn (M4.1) and distribution selection
  (M4.2) have real, persisted, cross-checked results; methods note
  (`docs/methods/burn_distribution.md`) covers both plus the CRPS-vs-AIC
  rationale and the ENSO-conditioning honest-underperformance finding.
- `docs/STATUS.md` updated: M4 row now ✅, F09 now ✅, new M4 detail
  table, MLflow port quirk documented, "how to resume" now points at M5
  (C++ simulator — needs a toolchain decision).

---

## 2026-10-04 — Close the remaining gaps; M4.1 burn analysis on real data

Continuation of the same day, after resolving the backfill/VERIFY/MJO
blockers (two entries below). The user asked to fill any remaining gaps
and keep building.

- **IMD backfill: 1991-2020 now fully complete, zero gaps.** All 6 years
  that failed in the earlier run (1999/2000/2001/2009/2013/2019)
  succeeded on retry once the server recovered — confirmed the earlier
  failures were transient (IMD responded in 3-38s on retry, vs. hanging
  6+ hours on the very first, unprotected attempt). Now 31 years of real
  data on disk.
- **mq.specs.registry**: writes the resolved ContractSpec and one
  `contracts` row per listed series into the DB, from each contract's
  real launch calendar (not previously done — M1/M2 had only validated
  specs in memory, never persisted the contract calendar itself). Real
  data for both contracts: RAINCHNNAI Sep-Dec 2026, RAINMUMBAI Jun-Sep
  2026 (all four RAINMUMBAI series already expired this season).
- **M3 completed**: `mq.index.writer.write_index_values` and
  `mq.index.proxy.proxy_error`, closing out the two pieces STATUS.md had
  marked pending.
- **M4.1 historical burn analysis** (`mq.pricing.burn`): reconstructs
  every historical season's final CDR value via `compute_index`. Golden
  test hand-computes 3 synthetic seasons and cross-checks mean/median/sd
  against Python's `statistics` module.
- **Two real performance bugs found and fixed** while actually running
  this against 31 years of real data (not caught by any unit test, since
  small fixtures hide O(n) scaling problems):
  1. `nearest_cell` (3 duplicated implementations) sorted the *entire*
     multi-decade `rain_grid` — tens of millions of rows — to find a
     single nearest point. Consolidated into `mq.io.grid.nearest_cell`,
     which dedupes to ~5,000 distinct cells first: 12+ minutes -> 2.6s.
  2. `compute_index`'s daily lookup called `.filter()` once per
     (day, station) — thousands of calls for a multi-year loop, each
     paying per-call overhead independent of actual work. Replaced with
     vectorized joins + `mean_horizontal`. A single call over the full
     56M-row dataset: ~14s. All 8 golden tests still pass unchanged,
     confirming identical output.
  3. The first attempt at this burn analysis ran 16+ CPU-minutes without
     finishing before the fixes — killed rather than let it run
     indefinitely; a smaller test would never have surfaced this.
- **IMD real-time data: Sep 1 - Oct 3 2026, now complete** (33/33 days).
  Filled the remaining Sep 11-30 gap in two passes once the IMD
  real-time server recovered from the strain noted in the previous entry.
- **The actual live CDR index for RAINCHNNAI, computed end-to-end from
  real data for the first time this session**: season-LPA anchor =
  896.54mm (computed from the real 1991-2020+2023 base period), observed
  rainfall Sep1-Oct3 2026 = real IMD data, **observed_to_date = 815.3mm**
  as of 2026-10-03. Written to `index_values`, 99 rows (33 dates × 3
  active series: OCT26/NOV26/DEC26).
- **Real historical burn statistics, all 31 seasons** (no synthetic data
  anywhere in this number): n=31, mean=905.6mm, median=843.4mm, sd=388.5,
  P5=449.6, P25=647.9, P75=1049.9, P95=1699.0, skew=1.14 (right-skewed,
  as expected for rainfall totals), ES-lower-5%=345.3, ES-upper-5%=1952.8.
  Written to `valuations` (method=burn, measure=P) for all 3 active
  series via the new `mq.pricing.writer.write_burn_valuation`.
- **Measured:** `make check` green — 75/75 tests pass, 0 lint issues,
  `mypy --strict` clean on 46 source files.

**Next task:** M4.2 (distribution fitting: Gamma/Lognormal/KDE/bootstrap
against the real 31-season burn sample, with rolling-origin CV) is the
natural continuation of M4. M5 (C++ simulator) needs a toolchain decision
first (pybind11/scikit-build-core/OpenMP not yet installed).

---

## 2026-10-04 — M3.1 index engine; IMD backfill completes; real climatology

Continuation of the same day's work, after the VERIFY/M2 entry below.

- **M3.1**: `mq.index.lpa.compute_daily_lpa` (climatological per-day LPA
  from `rain_grid`) and `mq.index.engine.compute_index` (the real CDR
  algorithm: spot = season-LPA anchor + cumulative daily deviation,
  exactly per the official product notes). Pure functions, no I/O.
  - Golden test (`tests/golden/test_index_engine_golden.py`) hand-computed
    a 3-day example before encoding expected values. This caught a real
    bug: `season_lpa_total`'s `month*100+day` key overflowed polars'
    int8 dtype (max 127; Sep 1 = 901), silently wrapping and zeroing
    every season total. Fixed by casting to Int32 first — the kind of
    bug that golden tests exist to catch.
- **IMD backfill 1991-2020 completed**: 23/30 years ingested this run
  (plus the pre-existing 2023) = **25 years of real gridded rainfall**.
  Missing 1999/2000/2001/2009/2013/2019 — transient IMD server
  timeouts/connection resets, not permanent gaps; individually rerunnable.
  The per-year subprocess-timeout design (logged in the previous entry)
  worked as intended throughout — no hangs, every stuck year was skipped
  and logged within 120s.
- Attempted to also backfill the live season's real-time data
  (Sep 1 - Oct 4 2026) to get a complete current CDR value. Got Sep 1-10
  and Oct 1-3 before the IMD real-time server started timing out
  consistently — stopped retrying rather than keep hammering a public
  government server under evident strain from this session's traffic.
  Sep 11-30 remains a gap; `compute_index` correctly refuses to produce a
  value across it rather than silently interpolating.
- **Wrote a real multi-year `clim_v1` v0.3.0 ledger row** for RAINCHNNAI
  using the full 25-year backfilled climatology: quantiles P5=357mm,
  P25=584mm, P50=697mm, P75=1027mm, P95=1769mm — a genuine distribution,
  not the earlier n=1 degenerate point. `mq ledger verify`: 3 rows (v0.1.0
  proxy-window, v0.2.0 real-window n=1, v0.3.0 real-window n=25), chain
  intact. Exported to `ledger/2026/10/04.jsonl`.
- **Measured:** `make check` green — 59/59 tests pass, 0 lint issues,
  `mypy --strict` clean on 40 source files.

**Next task:** fill the Sep 11-30 real-time gap (once the IMD server
settles) to get a complete live CDR index value; wire `compute_index`
output to `index_values` DB writes; or move to M4 (burn/distribution
pricing), which only needs the index engine's output shape, not live data.

---

## 2026-10-04 — Resolve VERIFY, M2 market-data pipeline

Continuation of the same day's work: resolved the three blockers logged
at the end of the previous entry, then moved to M2.

- **VERIFY V1-V11 closed for real.** Searched ncdex.com directly (public
  downloads, robots.txt allows everything) and found the actual official
  documents: Contract Specifications, Product Notes (CDR spot-price
  methodology), and launch circulars for both RAINCHNNAI and RAINMUMBAI,
  plus the UDiFF bhavcopy format spec. 9 PDFs registered and hashed in
  `specs/sources/raw/`. Rewrote both `specs/contracts/*.yaml` from DRAFT
  to fully resolved — `mq specs validate` now passes both without
  `--allow-draft`.
  - Real values corrected an earlier guess: RAINCHNNAI's period is
    **Sep 1-Dec 31**, not the Oct 1 proxy used in the first ledger row.
    RAINMUMBAI's Jun 1-Sep 30 proxy guess turned out correct.
  - LPA base periods: Chennai 1971-2020, Mumbai 1991-2020 (both IMD
    climatological normals, stated in the product notes).
  - Wrote a new `clim_v1` v0.2.0 ledger row for RAINCHNNAI using the real
    period (old v0.1.0 row kept — ledger is append-only). Chain verified:
    2 rows, intact.
  - V12 (data licensing) stays open — no document states explicit terms.
- **IMD backfill 1991-2020** (the WMO/IMD 30-year climate-normal period,
  also RAINMUMBAI's own cited LPA window) started as a background job.
  First attempt hung 6+ hours on a stalled connection (imdlib sets no
  request timeout) — killed it and rewrote the backfill to run each year
  in a subprocess with a 120s timeout, skipping and logging instead of
  blocking. Confirmed working: 1991 took 3s on retry (the earlier hang
  was a transient stall, not a real server limitation). Running at commit
  time; some years in the 1998-2001 range timed out and were skipped
  (rerunnable individually later).
- **M2**: NCDEX market-data ingestion pipeline (`mq.pipelines.ncdex`).
  Found and registered the real UDiFF Final Bhav Copy column format
  (34 columns, ISO tags) from NCDEX's own "Consolidated File format"
  circular. Built parse → filter-to-contracts → normalise-to-
  market_quotes → DQ-gate → upsert, tested against a schema-accurate
  synthetic fixture (live fetch isn't available — see below).
  - Added DQ05 (stale data), DQ06 (unknown contract code), DQ07 (silent
    raw-file revision), DQ10 (settle outside the real 6% DPL band from
    VERIFY V7) to `mq.pipelines.dq`. DQ08/DQ09 deferred to M3 (need the
    index engine). `DQGateFailedError` moved from `imd.py` to `dq.py`
    since it's shared, not IMD-specific.
  - **Live bhavcopy fetch is blocked**: ncdex.com/markets/bhavcopy's
    backend (`/api/bhavcopy`) sits behind a JS fingerprint/bot-detection
    challenge — confirmed directly in the page's own served JS
    (`Fingerprint.start("/__verify/fp", "url=%2Fapi%2Fbhavcopy", ...)`).
    Not worked around — same policy as the earlier BoM/MJO decision:
    scripting past an explicit anti-bot control isn't something to do
    quietly. The pipeline is fully built and tested against the real
    schema; it just needs a manually-downloaded CSV (or a future real
    browser session) to go live.
- Checked NCDEX's robots.txt: `Disallow:` (empty) — no restriction there;
  the blocker is specifically the bot-detection layer, not robots.txt/ToS.
- **Measured:** `make check` green — 55/55 tests pass (up from 45),
  0 lint issues, `mypy --strict` clean on 38 source files.

**Gate status:** M1's gate was already met; this entry closes out its
remaining open items (real specs, not drafts). M2's gate ("DQ gate blocks
on bad data") is met for the pipeline logic (tested); not yet exercised
on real NCDEX data pending the fetch blocker.

**Next task:** M3 (index engine) is unblocked now that the real CDR
methodology is known — recommended next step. Alternatively: resolve the
bhavcopy/MJO fetch blockers if real market/MJO data matters before M3.

---

## 2026-10-04 — M1.1–M1.4 — Specs, climate ingestion, ledger live

- **M1.1** Source register (`mq.specs.sources`, `mq sources add`/`list`):
  SHA-256 content-addressed storage, YAML sidecar + `sources`/`raw_files`
  DB rows. 4 unit + 1 integration test.
- **M1.2** `ContractSpec` model (`mq.specs.contract`) with a `TODO_VERIFY`
  sentinel on every VERIFY-dependent field; loader (`mq.specs.loader`)
  rejects drafts unless `--allow-draft`; `mq specs validate` CLI. DRAFT
  YAMLs written for RAINCHNNAI and RAINMUMBAI
  (`specs/contracts/{code}/2026-10-04-draft.yaml`). 4 unit tests.
- **M1.3** Climate ingestion:
  - Added `imdlib` dependency (~150MB incl. matplotlib/scipy/xarray) —
    confirmed with you first per the project's own >50MB rule.
  - `mq.pipelines.dq`: DQ01 (missing dates), DQ02 (duplicate keys), DQ03
    (value range), DQ04 (schema drift), generic over any dataset; persists
    to `dq_results`. 10 unit + 1 integration test.
  - `mq.pipelines.imd`: IMD 0.25° rainfall, historical (`imdlib.get_data`)
    and near-real-time (`imdlib.get_real_data`) paths, both DQ-gated
    before Parquet write. **Measured, real data:** 2023 full year — 1.81M
    land-cell-days, all 365 calendar days present, DQ gate passed.
    2026-10-01→03 (NE monsoon onset, real-time product) — 14,892 rows, DQ
    gate passed.
  - `mq.pipelines.climate_idx`: ONI/DMI/MJO parsers. **Measured, real
    data:** ONI 920 rows (1950-01 → 2026-08), DMI 1877 rows (1870-01 →
    2026-05), both through the DQ gate and written to Parquet. MJO parser
    implemented and unit-tested against a captured real-format fixture,
    but live fetch is blocked — bom.gov.au returns an explicit
    "automated access blocked" page for this network, on the data URL
    *and* their own help page. Not worked around (would mean evading an
    explicit anti-scraping control); logged as an open blocker.
- **M1.4** Ledger goes live:
  - `mq.ledger.hashing`: canonical JSON + `payload_sha256`/`row_hash`
    two-hash scheme. 5 unit tests.
  - `mq.ledger.writer`: idempotent per (contract, as_of, model_id,
    model_version); correctly links `prev_hash` to the prior row's
    `row_hash` (or genesis). `mq.ledger.verify`: recomputes the whole
    chain. 3 integration tests, including a deliberately-forged row
    (direct INSERT with a wrong `prev_hash`) that `verify_chain()`
    correctly flags — proving the chain catches tampering that the
    DB-level trigger (M0) doesn't cover (INSERT isn't blocked, only
    UPDATE/DELETE).
  - `mq.forecasting.climatology`: `clim_v1`, empirical climatology of
    remaining-period rainfall from the nearest available grid cell. 3
    unit tests.
  - `mq.ledger.export`: writes `ledger/YYYY/MM/DD.jsonl`. 2 integration
    tests.
  - `mq ledger verify` / `mq ledger export` CLI commands.
  - **Real ledger row written**: RAINCHNNAI, `clim_v1` v0.1.0, as_of
    2026-10-04, target `remaining_rain_mm`, `data_version=imd-2023-only-n1`
    (honestly labelled: n=1 climatology sample, proxy grid cell — see
    docs/STATUS.md for why). `mq ledger verify` → "OK — 1 rows, chain
    intact." Exported to `ledger/2026/10/04.jsonl`.
  - RAINMUMBAI: no row written — its proxy season (Jun-Sep) is already
    closed for 2026; writing a "remaining rain" forecast for a closed
    season would be meaningless. Revisit per docs/STATUS.md.
- **Measured:** `make check` green — 0 lint issues, `mypy --strict`
  clean on 37 source files, **45/45 tests pass** (up from 7 after M0).

**Gate status:** M1's stated gate ("ledger ≥ 1 verified daily row per
live contract; `mq ledger verify` passes") is met for RAINCHNNAI, the one
contract with an actually-open proxy season today. RAINMUMBAI and real
VERIFY closure remain open — both documented in docs/STATUS.md as
blocked on you (contract-spec PDFs; a backfill-scope decision; a MJO
network/access decision).

**Next task:** your call — supply the NCDEX PDFs, decide the IMD backfill
scope, or move ahead to M2 (market data ingestion + DQ05-DQ10) on the
current DRAFT specs.

---

## 2026-10-04 — M0.1–M0.3 — Scaffold complete

- Repo created at `~/Documents/MonsoonQuant`, layout per SPEC §5 (specs/,
  core/, src/mq/*, web/, tests/{unit,golden,property,statistical,integration,e2e},
  notebooks/, research/, paper/, docs/, .github/workflows/).
- git initialized locally (branch `main`), `.gitignore`, `.env.example`.
- uv workspace (`pyproject.toml`, Python 3.12 pinned): `uv sync` installs 44
  packages clean.
- Makefile with bootstrap/check/test-golden/bench/ingest/reproduce/dev/down
  targets (ingest/reproduce are forward stubs — the CLI subcommands they
  call don't exist until M1/M15).
- `.pre-commit-config.yaml` (ruff, mypy, clang-format, gitleaks); installed
  locally. `.github/workflows/ci.yml` skeleton (lint/types, unit+golden+
  property, integration-with-postgres-service, gitleaks; web/C++ jobs
  commented as TODO until M5/M13).
- `docker-compose.yml`: postgres:16 (host port **5433**, not 5432 — see
  docs/DECISIONS.md) + mlflow. Both verified running locally via colima.
- `mq` CLI skeleton (Typer): `mq --help`, `mq version` — verified working.
- `src/mq/config.py` (pydantic-settings), `src/mq/logging.py` (structlog,
  JSON renderer off-TTY).
- `src/mq/io/asof.py`: the as_of-aware data access layer
  (`enforce_as_of`, `assert_no_lookahead`, `read_as_of`). 5 unit tests in
  `tests/unit/test_io_asof.py`, including one that proves a look-ahead read
  raises `AsOfViolationError`.
- Alembic migrations (`src/mq/db/migrations/`, config at
  `src/mq/db/alembic.ini`) for all 11 §6.1 tables (sources, raw_files,
  contract_specs, contracts, market_quotes, index_values, model_runs,
  valuations, mpr_estimates, dq_results, prediction_ledger) plus a second
  migration adding the prediction_ledger append-only trigger
  (`mq_prediction_ledger_block_mutation`, blocking UPDATE and DELETE).
  Applied to the local Postgres (`alembic upgrade head` — both revisions
  ran clean).
- `tests/integration/test_ledger_immutability.py`: 2 tests proving the
  trigger actually blocks UPDATE and DELETE against a live Postgres
  (caught as `sqlalchemy.exc.ProgrammingError` with message
  `"prediction_ledger is append-only: ..."`).
- **Measured:** `make check` passes clean — ruff (0 issues), ruff format
  (33 files formatted), `mypy --strict src/mq` (0 issues, 23 source files),
  `pytest -q` (7 passed: 5 unit + 2 integration).
- Two environment gotchas hit and fixed, logged in docs/DECISIONS.md:
  (1) port 5432 conflict with a pre-existing Homebrew `postgresql@15`
  service → moved to 5433; (2) macOS `UF_HIDDEN` flag on uv's editable-
  install `.pth` file is skipped by CPython 3.12's `site.py`, breaking
  `import mq` → Makefile now exports `PYTHONPATH=$(CURDIR)/src`.
- Copied the three planning documents into `docs/`: `SPEC.md` (source of
  truth), `PROMPTS.md`, `IMPLEMENTATION_PLAN_V1.md` (superseded by SPEC.md
  per its own header, kept for reference).

**Gate status:** M0 scaffold gate met (`make check` green, services up).
M1 gate (ledger ≥ 1 verified daily row per live contract, `mq ledger
verify` passes) is **not yet attempted** — that's the next milestone.

**Next task:** M1.1 — source register + VERIFY V1–V12 (needs the user to
obtain the official NCDEX contract-spec PDFs; see docs/VERIFY.md).
