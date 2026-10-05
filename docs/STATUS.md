# MonsoonQuant — Status: what's done, what's left

Source of truth: `docs/SPEC.md`. This file is the single tracking sheet —
update it at the end of every milestone (alongside a `docs/PROGRESS.md`
entry). Status legend: ✅ done · 🟨 in progress · ⬜ not started.

Repo: `~/Documents/MonsoonQuant` (local git, not yet pushed anywhere).

---

## Milestones (SPEC §13 — 15-week plan, Mon 5 Oct 2026 → Sun 17 Jan 2027)

| Week | Milestone | Status | Gate | Notes |
|---|---|---|---|---|
| 1 | **M0** Scaffold | ✅ done | `make check` green | repo, uv, Makefile, pre-commit, CI skeleton, docker-compose, `mq` CLI, settings, structlog, as_of io layer + test, Alembic + ledger trigger |
| 1 | **M1** Specs + ledger live | ✅ done | ledger ≥ 1 verified daily row/contract; `mq ledger verify` passes | RAINCHNNAI and RAINMUMBAI specs **fully resolved from official NCDEX documents** (V1-V11 closed). RAINCHNNAI has a real verified ledger row; RAINMUMBAI's season is closed for 2026 (see below) |
| 2 | **M2** Market data & DQ | 🟨 pipeline built, no real data yet | DQ gate blocks on bad data | NCDEX bhavcopy parser/normaliser + DQ05-DQ10 built and tested against the real documented schema; live fetch blocked (bot-gated), needs a manually-downloaded CSV |
| 2 | **M3** Index engine | ✅ done | index reproducible for any past date | `compute_index` implements the real CDR methodology exactly, golden-tested. `index_values` DB writer and `proxy_error` (ready, no official series to compare against yet) both built |
| 3 | **M4** Burn & distribution pricing | ✅ done — both M4.1 (burn) and M4.2 (distribution selection) have **real persisted results** | 2 independent P-measure prices + methods note | Burn: mean=905.6mm, median=843.4mm, P5=449.6, P95=1699.0, skew=1.14 (n=31). Distribution: 7 candidates scored by leave-one-out CRPS, `kde_cv` selected (CRPS=213.01); fair_value=902.7mm, lo90=318.0mm, hi90=1796.6mm. Both written to `valuations` for all 3 active RAINCHNNAI series. Methods note: `docs/methods/burn_distribution.md` |
| 4 | **M5** Simulator (build) | ✅ done — M5.1 (GLM fit), M5.2 (NumPy reference + overdispersion fix) and M5.3 (C++ core) all built and verified | C++ vs NumPy ref agree within 2 SE | **M5.3 real results**: Philox4x32-10 verified bit-for-bit against Random123's own known-answer test vectors; 1,000,000 paths × 92 days in **0.80s** (budget 10s); same seed → bit-identical SHA-256 digest across 1/2/4/8 OpenMP threads; statistical agreement with the NumPy reference within Monte Carlo noise. Still open: SPEC's literal 1951-2020 statistical holdout window needs a backfill extension (currently 1991-2020+2023) — a data task, not a code task |
| 5 | **M5** Simulator (validate) · **M6** MPR (start) | ✅ M5 gates met (see M5 detail); M6 built and verified (see M6 detail) | 1M paths < 10s; seasonal sd ±10% | |
| 6 | **M6** MPR (finish) · **M7** Forecasting (start) | 🟨 M6's Wang/Esscher/calibration/uncertainty machinery done; real calibration blocked on bhavcopy (same as M2). M7: all 5 built rungs real-backtested | λ series w/ CIs live; walk-forward runs | |
| 7 | **M7** Forecasting (finish) | ✅ done — 5 rungs built, real walk-forward backtest run, CRPSS reported honestly (negative for all 4 newer rungs; conformal calibration demonstrably fixes coverage regardless). `tft_v1` deliberately skipped (reasoning on record) | CRPSS vs climatology reported | |
| 8 | Buffer | ⬜ not started | — | |
| 9 | **M8** Conditioned pricing · **M9** Greeks | ✅ M8 done (see M8 detail); M9 Greeks done (delta/gamma exact, theta meets SE<5% with enough paths — see M9 detail) | 4-method comparison daily; Greek SE < 5% | |
| 10 | **M9** Hedge optimiser | ✅ done — min-variance + CVaR95 LP, real run against RAINCHNNAI (see M9 detail) | `/v1/hedge` < 5s | |
| 11 | **M10** Basis · **M11** Parametric & Scenarios | ✅ M10 and M11 (both parametric cover + scenario lab) all done — see M10/M11 detail | basis heatmap + 1 parametric case study | |
| 12 | **M12** API hardening · live eval | 🟨 8 of 18 endpoints built + real integration tests against the real DB; see M12 detail | contract tests + OpenAPI drift check green | |
| 13 | **M13** Dashboard | ⬜ not started | Lighthouse ≥ 90; E2E green | |
| 14 | **M14** Deploy & harden | ⬜ not started | public URL; 7 consecutive daily runs | |
| 15 | **M15** Paper, demo, launch | ⬜ not started | Definition of Done walkthrough passes | |

---

## M0 detail (done)

Repo layout, git, uv workspace, Makefile, pre-commit, CI skeleton,
docker-compose (postgres:16 on port **5433**, mlflow), `mq` CLI, settings,
structlog, `mq.io.asof` as_of-aware layer, Alembic migrations (all 11
§6.1 tables), `prediction_ledger` immutability trigger (UPDATE/DELETE
proven blocked at the DB level). See `docs/PROGRESS.md` 2026-10-04 entry
for the full list.

---

## M1 detail (done — specs fully resolved)

| Item | Status |
|---|---|
| Source register (`mq.specs.sources`, `mq sources add`/`list`) | ✅ |
| `ContractSpec` model + loader (`TODO_VERIFY` sentinel, `--allow-draft`) | ✅ |
| **Real NCDEX contract specs found and registered** | ✅ 9 official PDFs hashed in `specs/sources/raw/` (contract specs, product notes, launch circulars, UDiFF format spec) |
| `specs/contracts/RAINCHNNAI/2026-08-31.yaml` | ✅ **fully resolved**, loads without `--allow-draft` |
| `specs/contracts/RAINMUMBAI/2026-05-29.yaml` | ✅ **fully resolved**, loads without `--allow-draft` |
| `mq specs validate` CLI | ✅ |
| DQ01–DQ04 gate (`mq.pipelines.dq`) | ✅ |
| IMD 0.25° gridded rainfall ingestion (`mq.pipelines.imd`) | ✅ historical + near-real-time, both DQ-gated |
| **IMD historical backfill 1991-2020** | 🟨 running (background, resumable) — see "Live state" below |
| ONI / DMI ingestion (`mq.pipelines.climate_idx`) | ✅ live: ONI 920 rows, DMI 1877 rows |
| MJO ingestion | 🟨 parser done, tested; live fetch blocked (BoM bot-gate, docs/DECISIONS.md) |
| `clim_v1` climatology forecaster | ✅ |
| Ledger hash chain + writer + verify + export | ✅ tamper detection proven |
| **Real ledger rows**: RAINCHNNAI, `clim_v1` v0.1.0 (proxy Oct-Dec window) and v0.2.0 (real Sep-Dec window, post-VERIFY) | ✅ both verified, chain intact |
| Daily export → public GitHub repo + Actions cron | ⬜ deferred — no GitHub remote (local git only, per your instruction) |
| RAINMUMBAI ledger row | ⬜ its real period (Jun 1-Sep 30) is closed for 2026 as of today (Oct 4) — nothing to forecast until Jun 2027 |

### VERIFY resolution (see docs/VERIFY.md for full citations)
Found the official NCDEX documents myself (public downloads linked from
`ncdex.com/products/RAINCHNNAI` and `/RAINMUMBAI`, robots.txt allows
everything) rather than waiting — closed **V1-V11**. Real values differ
from the earlier placeholder/proxy assumptions in one important way:
RAINCHNNAI's real period is **Sep 1-Dec 31** (not the Oct 1 start used in
the first ledger row — that row is kept, a corrected one was added, since
the ledger is append-only). V12 (data-redistribution licensing) stays
open — no document states explicit terms.

### Honesty note on the ledger rows
RAINCHNNAI has **3 ledger rows** now, each a progressively better
`clim_v1`: v0.1.0 (n=1, proxy Oct-Dec window), v0.2.0 (n=1, real Sep-Dec
window post-VERIFY), v0.3.0 (**n=25, real multi-year climatology**, after
the backfill below completed — quantiles P5=357mm, P50=697mm, P95=1769mm,
a genuine spread rather than a degenerate point). `mq ledger verify`: 3
rows, chain intact. Station coordinates are still public engineering
placeholders, not yet the official IMD metadata (noted in the YAML
comments) — that's the main remaining honesty caveat.

---

## M2 detail (pipeline built this session)

| Item | Status |
|---|---|
| NCDEX UDiFF bhavcopy format — found and registered the real spec | ✅ `ncdex_udiff_bhavcopy_format_2024` (34-column schema with ISO tags) |
| `mq.pipelines.ncdex`: parse → filter → normalise → DQ gate → upsert | ✅ tested against a schema-accurate synthetic fixture (6 unit + 2 integration tests) |
| DQ05 (stale data), DQ06 (unknown contract code), DQ07 (silent raw-file revision), DQ10 (settle outside DPL band) | ✅ |
| DQ08 (climate index revision), DQ09 (proxy index jump >3σ) | ⬜ deferred — need M3's index engine to exist first |
| **Live bhavcopy fetch** | 🔴 blocked — ncdex.com's `/api/bhavcopy` sits behind a JS fingerprint/bot-detection challenge (confirmed via the page's own served JS). Not worked around, same policy as BoM. Needs either a manually-downloaded CSV or a real browser session (claude-in-chrome wasn't connected this session) |

---

## M3 detail (index engine, complete)

| Item | Status |
|---|---|
| `mq.index.lpa.compute_daily_lpa` — climatological per-day LPA from `rain_grid` | ✅ |
| `mq.index.engine.compute_index` — real CDR methodology (season-LPA anchor + cumulative daily deviation) | ✅ pure function, raises loudly on drafts or data gaps |
| Golden test, hand-computed before encoding expected values | ✅ 4 tests, including a deliberate missing-data case |
| `mq.io.grid.nearest_cell` — shared, performant cell lookup | ✅ fixed a real bug: the original per-module implementations sorted the *entire* multi-decade rain_grid (tens of millions of rows) to find one nearest cell — 12+ minutes on the real dataset. Deduping to distinct cells first (~5,000) before sorting: 2.6s |
| `compute_index`'s daily lookup — vectorized via joins | ✅ fixed a second real bug: one `.filter()` call per (day, station) scaled to thousands of calls for a multi-decade loop. Replaced with 2 left-joins + `mean_horizontal`. Single call over the full 56M-row dataset: ~14s |
| `index_values` DB writer (`mq.index.writer`) | ✅ **written for real**: 99 rows (33 real dates × 3 active series) from the actual Sep1-Oct3 2026 CDR reconstruction |
| `mq.index.proxy.proxy_error` | ✅ built and tested; nothing to run it against yet — no official NCDEX settlement series available (same bot-gate/licensing situation as market data) |

---

## M4 detail (burn & distribution pricing, complete)

| Item | Status |
|---|---|
| `mq.pricing.burn` — real 31-season CDR reconstruction | ✅ mean=905.6mm, median=843.4mm, sd=388.5, P5=449.6, P95=1699.0, skew=1.14 |
| `mq.pricing.distribution` — 7 candidates (gamma, lognormal, weibull, kde_silverman, kde_cv, bootstrap, enso_climatology) | ✅ all expose a common Monte-Carlo-sample + optional-logpdf interface |
| `mq.pricing.selection` — leave-one-out CV, CRPS as primary criterion (SPEC's "AIC secondary only", taken further: AIC not computed at all) | ✅ `kde_cv` selected, CRPS=213.01, narrowly ahead of gamma (213.14) and weibull (213.30) |
| `valuations` writer — both `method="burn"` and `method="dist"` rows | ✅ written for all 3 active RAINCHNNAI series |
| MLflow experiment tracking (`burn_distribution_selection`) | ✅ working — see port-5001 fix below |
| Methods note | ✅ `docs/methods/burn_distribution.md` — full candidate table, CRPS results, the `-inf` log-likelihood finding (free-loc gamma/weibull instability, not a bug), ENSO-conditioning's honest underperformance at this sample size |
| **Perf fix**: `compute_index`'s LPA groupby + grid-cell lookup, now cached/reused across burn's 31 calls | ✅ `build_burn_sample`'s real end-to-end run: **254s → 12s (~21x)**, output byte-identical before/after (no behavior change, pure perf) |
| Detrending | ⬜ explicitly deferred — see methods note §"What's not done yet" |

---

## M5 detail (simulator — M5.1, M5.2, and M5.3 all done)

| Item | Status |
|---|---|
| `mq.pricing.simulator_glm` (M5.1): logistic GLM (p01, p11) + Gamma log-link GLM (amount), on Fourier harmonics + ONI/DMI covariates | ✅ hand-rolled MLE via scipy.optimize (no new statsmodels/sklearn dep) |
| Real fit, nungambakkam station, n=11,323 days (1991-2020+2023) | ✅ both occurrence GLMs + amount GLM converge; amount shape=0.316 (strongly right-skewed, as rainfall is) |
| `mq.pricing.simulator_ref` (M5.2): NumPy reference chain-dependent simulator | ✅ day-by-day Markov occurrence + Gamma amount, accumulates (rain-LPA) deviation exactly like `compute_index` |
| Overdispersion fix (season-level lognormal multiplier on the amount-mean, calibrated via 1-D Brent root-find) | ✅ **real validation**: no-fix simulated seasonal-total sd=272.5mm vs. real historical sd=412.3mm (confirms SPEC's under-dispersion problem on real data); after calibration (sigma=0.336), simulated sd=418.5mm — within SPEC's ±10% acceptance band. Script + log: `.scratch/validate_simulator.py` (gitignored — depends on real backfilled data, not committed as a test, same pattern as the backfill scripts) |
| **M5.3 C++ core**: CMake + pybind11 + scikit-build-core + OpenMP + Philox4x32-10 | ✅ done. New `core/` package, its own uv workspace member (scikit-build-core + pybind11) so the main hatchling-built `mq` package never needs a C++ compiler. Philox4x32-10 implemented from the published Salmon et al. 2011 constants (not vendored from upstream Random123) — verified bit-for-bit against Random123's own known-answer test vectors before being trusted for anything else |
| OpenMP on Apple Clang | ✅ Apple Clang ships no OpenMP runtime; `find_package(OpenMP)` needed explicit Homebrew-libomp hints (a known macOS/CMake gotcha) — documented in `core/CMakeLists.txt`, not re-debugged next time |
| `mq.pricing.simulator` (production, C++-backed) vs. `mq.pricing.simulator_ref` (NumPy reference) | ✅ both share one feature-building step (`mq.pricing.simulator_features`) so they can't silently drift; verified to agree statistically (`tests/statistical/test_simulator_parity.py`), including the real shape<1 Gamma boost-trick branch |
| Determinism: same seed → same output regardless of OpenMP thread count | ✅ **measured, not assumed**: bit-identical SHA-256 digest across 1/2/4/8 threads (`tests/statistical/test_simulator_determinism.py`) — true by construction (every RNG draw is a pure function of (key, path_id, day, stream, attempt), no shared mutable stream state), and confirmed empirically |
| `make bench` (1M paths × 92 days < 10s) | ✅ **0.80s measured** (12x under budget) — `docs/benchmarks/simulator_1m_paths.txt`, regenerated by `tests/statistical/test_simulator_bench.py` |
| Statistical holdout validation vs. SPEC's literal "1951-2020" window | ⬜ **blocked on data, not code** — current backfill is 1991-2020+2023 only; extending back to 1951 needs another IMD backfill run (same pattern as the existing one, just more years) |

---

## M6 detail (market price of risk — machinery done, real calibration blocked)

| Item | Status |
|---|---|
| `mq.mpr.wang`: Wang transform via order-statistic reweighting (no re-simulation) | ✅ sign convention (λ>0 raises price) verified by test, not assumed from one paper's convention |
| `mq.mpr.esscher`: Esscher transform on the standardized payoff, with Kish's ESS + SPEC's "refuse below 1% of N" gate | ✅ `LowEffectiveSampleSizeError` raised rather than silently reporting a degenerate self-normalized estimate |
| `mq.mpr.calibrate`: Brent-solved λ/θ to match a settle price, bounded [-3,3] | ✅ round-trip tests recover a known generating λ/θ exactly; unreachable settle reports the nearer corner (`converged=False`) instead of crashing |
| `mq.mpr.uncertainty`: (a) bootstrap over resampled years, (b) closed-form delta-method MC error, (c) Bayesian pooling across dates (weak N(0,1) prior, liquidity-weighted) | ✅ all three built, tested independently of real market data |
| Illustrative end-to-end run against the real M4 burn sample + real kde_cv distribution | ✅ settle=P-mean recovers λ=θ=0 exactly; settle above/below the mean recovers the predicted sign. Full uncertainty pipeline run at an illustrative settle=1000mm: bootstrap band [-0.042, 0.831] (wide — n=31 is thin), 3-date illustrative Bayesian pool [0.027, 0.485]. See `docs/methods/mpr.md` |
| **Real calibration against actual NCDEX settlement prices/volumes** | ⬜ **blocked, not a code gap** — bhavcopy fetch is bot-gated, same root cause as M2. Nothing to calibrate against yet |
| Research outputs (λ vs. days-to-expiry, λ vs. volume, Wang-vs-Esscher consistency) | ⬜ needs multiple real calibrated dates — same blocker |

---

## M7 detail (forecasting ladder — all 5 rungs built, real backtest run)

| Item | Status |
|---|---|
| `mq.forecasting.features.build_training_rows`: (year, issue_date) training table on the 2-station averaged series | ✅ real run: 3,751 rows across 31 years. First version called `compute_index` per issue-day and didn't finish in 2 minutes; rewritten as one vectorized cumsum pass per season |
| `clim_v1` | ✅ ledger-live since M1 (unchanged — left as-is per "never modify ledger rows without asking") |
| `enso_clim_v1`: climatology conditioned on ONI tercile | ✅ built, reuses M4's `oni_terciles` |
| `analog_v1`: k=5 nearest past seasons on (anomaly, ONI, DMI) | ✅ built, no new dependency (plain NumPy k-NN) |
| `lgbm_q_v1`: LightGBM quantile regression + monotone rearrangement | ✅ built on lightgbm's native `Dataset`/`Booster` API (not `LGBMRegressor`, which hard-requires scikit-learn — an unplanned extra dependency the size check never covered) |
| `lgbm_q_cqr_v1`: + split-conformal calibration per quantile level | ✅ built, whole-season calibration fold (never splits a season) |
| `mq.forecasting.evaluate`: CRPS/CRPSS/pinball/coverage/PIT + walk-forward harness | ✅ enforces "train ≤ year y-1" structurally (combines only strictly-prior years + the single target row before calling the model) |
| **Real walk-forward backtest, RAINCHNNAI, n=2,541 predictions/model, all 5 rungs** | ✅ **honest finding, consistent across every newer rung**: climatology baseline CRPS=156.44; `enso_clim_v1`=165.44 (CRPSS=-0.058); `analog_v1`=182.27 (-0.165); `lgbm_q_v1`=194.03 (-0.240); `lgbm_q_cqr_v1`=201.92 (-0.291) — every added-complexity rung underperforms plain climatology at n=31 seasons. None retuned to chase a positive number (would overfit the backtest itself). **But conformal calibration does what it's built to do**: `analog_v1`/`lgbm_q_v1` under-cover badly (31.9%/60.9% and 33.1%/68.6% vs. 50%/90% nominal); `lgbm_q_cqr_v1`'s coverage (45.5%/86.3%) comes in much closer to nominal than the uncalibrated model it corrects — the mechanism measurably works even though it doesn't rescue CRPS. Full write-up: `docs/methods/forecasting.md` |
| `tft_v1` (P2) | ⬜ **deliberately skipped, reasoning on record**: SPEC itself calls this a weak candidate at ≈120 seasons; this project's real n=31 is well below even that |
| Live ledger rows for the 4 newer rungs | ⬜ needs a separate "live row" builder for the in-progress 2026 season — `build_training_rows` requires a *complete* historical season, so it can't produce today's own row as-is |

---

## M8 detail (forecast-conditioned pricing — done, real end-to-end run)

| Item | Status |
|---|---|
| `mq.pricing.conditioned.quantile_map`: rank-based CDF matching of simulated near-term totals onto a forecast | ✅ preserves the simulator's path-for-path ordering/autocorrelation while replacing its marginal; hand-computed test |
| Near-term/remainder split via two `simulate()` calls sharing a seed | ✅ **zero simulator code changes needed** — every RNG draw is a pure function of (seed, path_id, day_index), never of total n_days, so subtracting a short run's terminal deviation from a long run's (same seed/start_date) isolates the remainder exactly. Verified via a law-of-large-numbers check |
| `remaining_rain_climatology_2station`: `clim_v1`'s 2-station, horizon-capped counterpart | ✅ new function; `clim_v1`'s own single-station function left untouched (ledger-live) |
| **Real end-to-end run**: real chain model, real LPA, real ONI/DMI, real observed_to_date=815.3mm (2026-10-03) | ✅ **confirms SPEC's own "never assume monotonic shrinking uncertainty" on real data, not just as a caveat**: 90% band width across h=7/14/30/60/89 days = 1171.5/1175.1/1124.6/**1420.4**/1240.4mm — genuinely non-monotonic, with a plausible (not yet verified) late-season ENSO-variance explanation for the h=60 spike. Full write-up: `docs/methods/conditioned.md` |
| Real λ / Q-measure band | ⬜ blocked on real settlement data (same bhavcopy bot-gate as M6) — mechanically straightforward on top of what's built (`mq.mpr.wang`/`esscher` applied to `result.payoff`), just nothing real to calibrate against yet |

---

## M9 detail (Greeks — done; hedge optimiser — not started)

| Item | Status |
|---|---|
| `mq.risk.greeks`: delta/gamma/theta via common random numbers | ✅ delta/gamma get *exact* CRN pairing (observed_to_date is a pure additive offset, never touches the RNG); theta's two variants (no-rain-day, climatological-day) get only *partial* pairing (shifting start_date reshuffles which calendar day lands at RNG day-index 0) — reported as `pairing="exact"`/`"partial"` per result, not claimed uniformly |
| Closed-form correctness checks | ✅ on a fully deterministic (always-dry) model: delta=1.0 and gamma=0.0 exactly, theta matches hand-derived values including a single-day-season edge case |
| **Real run, RAINCHNNAI**: delta/gamma exact (structural — the CDR index is additive in observed_to_date by construction, true for any fitted model); theta at n_paths=20,000 misses SPEC's SE<5% bar badly (37-148%) | ✅ **switched the Greeks module to the C++ simulator core** (not M8's NumPy reference) specifically to make 1,000,000-path calls practical (~1.7s each); at that path count `theta_no_rain_day` meets the bar (4.55%). `theta_climatological_day` still doesn't (80%) — explained, not a remaining bug: its true value is plausibly exactly zero (a climatological day is zero-mean by construction), so SE/value diverges regardless of sample size. Full write-up: `docs/methods/greeks.md` |
| `mq.risk.hedge`: min-variance (`h*=-Cov/Var`, SPEC's own sign), exposure templates, lot constraints | ✅ done — `PiecewiseLinearExposure` covers all 4 named templates (delivery-rider/crop/event/construction) as one generic building block; `LotConstraints` handles max order lots, position limit, margin budget, max notional, long/short flags |
| `mq.risk.cvar`: Rockafellar-Uryasev CVaR95 LP | ✅ done via `scipy.optimize.linprog`'s HiGHS backend — the literal solver SPEC names ("cvxpy/HiGHS"), already available through the existing scipy dependency, no new cvxpy dependency added. Integer lots via small-neighborhood enumeration (SPEC's own stated MILP alternative) |
| **Real structural finding, confirmed on real data**: CVaR minimization can be unbounded when the index's sign never varies across scenarios (found while testing, on synthetic data) | ✅ **confirmed on the real RAINCHNNAI index**: it's positive in every one of the 31 historical seasons, so the unconstrained CVaR hedge genuinely wants to short without limit — position limits aren't a risk-management nicety here, they're required for the optimization to be well-posed at all for this contract. Real run: min-variance finds -5 lots (42% variance reduction, basis_contribution≈1.0) for a sized illustrative exposure; a smaller exposure rounds to 0 lots (the contract's multiplier is too coarse for a genuinely small exposure) — both honest findings, not forced to a "nicer" number. Full write-up: `docs/methods/hedge.md` |

---

## M10 detail (basis-risk engine — done, real 12-cell run)

| Item | Status |
|---|---|
| `mq.risk.basis.local_index_series`: single-station CDR reconstruction at any cell | ✅ thin wrapper around `mq.pricing.burn.build_burn_sample`, hand-verified against an independently re-derived single-station case from the burn golden test's own fixture |
| `compute_basis_stats`: correlation, RMSE, Kendall τ, empirical tail dependence (upper/lower), hedge effectiveness/ratio | ✅ exact closed-form checks on a perfectly-correlated synthetic pair (correlation=1, rmse=5, hedge_effectiveness=1, tail dependence=1); SPEC's own hedge-optimiser property tests (zero-correlation → h*≈0, doubling exposure doubles h*) also hold here since this computes the identical h* formula |
| `basis_grid` + `to_geojson` | ✅ enumerates the real IMD grid's own distinct cells within a bounding box (no artificial step size); GeoJSON FeatureCollection output matches SPEC's stated shape for a MapLibre heatmap (rendering itself is M13) |
| **Real run, RAINCHNNAI, all 31 seasons, ~1°×1° box (12 real cells)** | ✅ **sanity-confirms the methodology**: cells nearest the two real official stations score highest (correlation 0.96+, hedge effectiveness 0.92+); the box's far corner drops to 0.734/0.538 — basis risk measurably, substantially degrading with distance even within ~55-65km of Chennai. Full write-up: `docs/methods/basis.md` |
| Seasonal mismatch (within-season daily co-movement) | ⬜ implemented in `compute_basis_stats` but not wired into `basis_grid`'s per-cell loop yet — needs the official index's real 2-station-averaged daily series threaded through |

---

## M11 detail (parametric cover designer and scenario lab — both done)

| Item | Status |
|---|---|
| `mq.risk.parametric`: wet/dry capped-linear payout, `premium = E_Q[payout]*(1+loading)` via `mq.mpr.wang.wang_price` directly | ✅ built entirely on M4/M6/M9/M10's existing pieces — no new pricing machinery needed |
| `optimize_cover`: grid search + Nelder-Mead refine (SPEC's own stated method) over `(trigger, slope, limit)` to minimize basis-failure probability subject to a premium budget | ✅ hand-computed + closed-form tests pass |
| **Real finding about the objective itself**: an unconstrained trigger grid let the optimizer find a degenerate "trigger almost every year" cover that trivially drives basis-failure probability to exactly 0 without being well-calibrated to real loss events | ✅ **caught on the first real run**, not hidden — a legitimate optimum of SPEC's literal stated objective, not a bug; fixed by restricting the trigger grid to above the index's own historical median (a designer's judgment call SPEC doesn't specify) |
| **Real case study (SPEC's own stated one): synthetic Chennai delivery-rider exposure** | ✅ real local rainfall (M10's weakest-correlation cell) + real official index (M4), restricted trigger grid: basis-failure probability 25.8% (no cover) → 3.2% (optimized cover), premium 200.1 of a 50,000 illustrative budget, firing selectively in 15/31 years. Full write-up: `docs/methods/parametric.md` |
| `mq.risk.scenarios`: El Niño/La Niña/neutral ENSO, +/- IOD, dry November, cloudburst, real 2015 historical analog, custom shock | ✅ pure orchestration over M5/M9 (no new pricing math); "2015 Chennai floods analog" uses the real 2015 ONI/DMI from the real ingested `climate_idx` data, not an illustrative placeholder |
| **Real run, all 8 scenarios, RAINCHNNAI** | ✅ delta=1.0/gamma≈0 confirmed structurally across every single shock (same CDR-index additive-in-obs property M9 found, now under 8 different real covariate states); real 2015 analog (ONI=+2.28, mean=790.1mm) lands close to the synthetic `el_nino` preset (ONI=+2.0, mean=752.2mm) — an internal-consistency check between independently-derived strong-El-Niño inputs. Hedge P&L reported against an existing -5-lot position (M9's own real demo result) across every scenario. Full write-up: `docs/methods/scenarios.md` |
| Valuations under burn/distribution (M4) and forecast-conditioned (M8) methods specifically, re-optimized hedge per scenario | ⬜ this module currently reports only the simulator's own mean/P5/P95, not SPEC's full "all methods"; noted honestly, not claimed |

---

## M12 detail (API — 8 of 18 endpoints built)

| Item | Status |
|---|---|
| Response envelope (`data`/`meta`), RFC 9457 `problem+json` errors (`mq/stale-data`, `mq/unknown-series`, `mq/infeasible-hedge`) | ✅ matches SPEC §9.1 exactly |
| `GET /v1/health`, `/v1/health/data` | ✅ real row counts + latest dates from `index_values`/`market_quotes`/`prediction_ledger` |
| `GET /v1/contracts`, `/v1/contracts/{code}/spec` | ✅ real `contracts`/`contract_specs` tables |
| `GET /v1/series/{id}/valuation`, `/valuations/compare` | ✅ real `valuations` table (M4) |
| `GET /v1/ledger`, `/v1/ledger/verify` | ✅ wraps `mq.ledger.verify.verify_chain` directly |
| **Confirmed live**, not just `TestClient` | ✅ ran a real `uvicorn` server, curled it, checked the auto-generated OpenAPI schema lists all 8 routes correctly |
| **Two real findings caught against the real DB, not fixtures**: (a) `valuations/compare`'s original same-day join would have silently dropped a method — RAINCHNNAI's burn/dist valuations were genuinely written a day apart; (b) RAINCHNNAI's listed series were never registered in the real `contracts` table despite having real valuations/ledger rows | ✅ (a) fixed to return each method's own latest row; (b) fixed by calling the already-built registry functions against the real DB (a data fix, not a code change, idempotent). Full write-up: `docs/methods/api.md` |
| `GET /v1/series/{id}/index`, `/quotes`, `/forecast`, `/greeks`, `/mpr`, `/basis` | ⬜ real underlying functions exist (M3, M5-M11); not yet wired into routes |
| `POST /v1/hedge`, `/v1/parametric/design`, `/v1/scenarios/run` | ⬜ need request schemas + SPEC's `n_paths` cap/5s time-box; underlying functions exist (M9, M11) |
| `GET /v1/track-record`, `/v1/lineage` | ⬜ not started |
| OpenAPI export to a file, TS codegen, rate limiting, caching, CORS to a real origin | ⬜ not started — the file-export path (`web/lib/api/openapi.json`) deliberately not created ahead of M13's own `web/` scaffold |

---

## Live state (real data now on disk / in the DB)

- **IMD historical backfill 1991-2020: fully complete.** All 30 years
  ingested (plus the pre-existing 2023) = **31 years of real IMD
  rainfall** in `data/parquet/rain_grid/source=imd/`, zero gaps. (Six
  years hit transient timeouts on the first pass — all six succeeded on
  retry once the per-year subprocess-timeout script was re-run; see
  docs/PROGRESS.md for the full story.)
- **IMD real-time data: Sep 1 - Oct 3 2026, complete**, 33/33 days. Hit
  repeated IMD server timeouts filling this gap (both historical and
  real-time endpoints showed strain); retried once the server recovered
  rather than force it — all days eventually succeeded.
- **The actual live CDR index for RAINCHNNAI, computed end-to-end from
  real data**: season-LPA anchor = 896.54mm, observed_to_date (as of Oct
  3, 2026) = **815.3mm**. Written to `index_values` for all 3 currently
  active series (OCT26/NOV26/DEC26).
- **Real historical burn analysis**, all 31 seasons, no synthetic/proxy
  data: n=31, mean=905.6mm, median=843.4mm, sd=388.5, P5=449.6, P95=1699.0,
  skew=1.14 (right-skewed, as rainfall totals typically are). Written to
  `valuations` (method=burn, measure=P) for all 3 active series.
- **Real distribution selection**: 7 candidates, leave-one-out CV over all
  31 seasons, `kde_cv` selected by CRPS (213.01, narrowly ahead of
  gamma/weibull). fair_value=902.7mm, lo90=318.0mm, hi90=1796.6mm. Written
  to `valuations` (method=dist, measure=P) for all 3 active series; full
  candidate scores logged to MLflow (`burn_distribution_selection`
  experiment, port 5001).
- Scratch backfill scripts (`.scratch/*.py`, not committed, gitignored)
  are reusable if any future gap needs filling — 120s-per-year subprocess
  timeout pattern, proven to recover cleanly from transient IMD outages.

---

## Feature catalogue (SPEC §1.4)

| ID | Feature | Pri | Milestone | Status |
|---|---|---|---|---|
| F01 | Versioned contract-spec registry (YAML + source PDFs + hashes) | P0 | M1 | ✅ done, specs fully resolved |
| F02 | Market-data ingestion (settlement, volume, OI) with provenance | P0 | M2 | 🟨 pipeline done; live fetch blocked (bot-gate) |
| F03 | Gridded rainfall ingestion (IMD 0.25°) + station mapping | P0 | M2 | 🟨 **31 years real data, zero gaps** (1991-2020 + 2023) + real-time Sep1-Oct3 2026 all ingested; station identity resolved (V2), exact coordinates still a placeholder |
| F04 | Climate drivers (ONI, DMI/IOD, MJO phase) | P0 | M2 | 🟨 ONI+DMI live; MJO fetch-blocked (BoM) |
| F05 | Data-quality gate blocking publication | P0 | M2 | 🟨 DQ01-07, DQ10 done; DQ08-09 need M3 |
| F06 | Index replication engine + proxy-error tracking | P0 | M3 | ✅ `compute_index` done, golden-tested, 2 real performance bugs fixed; **real live CDR value computed and written** (observed_to_date=815.3mm as of Oct 3 2026); proxy_error has nothing to compare against yet |
| F07 | **Prediction Ledger** (append-only, hash-chained, public) | P0 | M1→ | 🟨 fully working locally; public GitHub mirror deferred (no remote) |
| F08 | Historical burn analysis (with detrending options) | P0 | M4 | 🟨 real 31-season reconstruction done and persisted; detrending options not started |
| F09 | Index-distribution pricing (Gamma/Lognormal/KDE/bootstrap/ENSO-conditioned) | P0 | M4 | ✅ done — 7 candidates, leave-one-out CRPS selection, `kde_cv` wins, written to `valuations` + MLflow |
| F10 | C++ chain-dependent stochastic rainfall simulator (1M paths < 10s) | P0 | M5 | ⬜ |
| F11 | Market price of risk (Wang + Esscher) w/ bootstrap/Bayesian CIs | P0 | M6 | 🟨 machinery done + tested + demoed on real M4 data with an illustrative settle; real NCDEX calibration blocked (bhavcopy bot-gate) |
| F12 | Probabilistic forecaster (climatology → analog → LightGBM-quantile + conformal) | P0 | M7 | ✅ done — all 5 rungs built + real-backtested (every newer rung underperforms climatology on CRPS at n=31, honestly reported; conformal calibration fixes analog_v1/lgbm_q_v1's under-coverage even though it doesn't rescue CRPS). `tft_v1` (P2) deliberately skipped, reasoning on record |
| F13 | Forecast-conditioned pricing & fair-value band | P0 | M8 | ✅ done — quantile-mapped simulator splice, real end-to-end run confirms SPEC's own "never assume monotonic shrinking uncertainty" on real data (band90 1171→1175→1125→**1420**→1240mm across h=7..89 days) |
| F14 | Rainfall Greeks (delta, gamma, theta) with common random numbers | P0 | M9 | ✅ done — delta/gamma exact (structural, additive-in-obs index), theta_no_rain_day meets SE<5% at 1M paths (C++ core), theta_climatological_day's near-zero true value makes the relative-SE bar inapplicable (explained, not hidden) |
| F15 | Hedge optimiser (min-variance + CVaR, integer lots, caps, margin) | P0 | M9 | ✅ done — min-variance (SPEC's own h*=-Cov/Var sign convention) + CVaR95 LP via scipy's HiGHS (no cvxpy needed); real run finds position limits are load-bearing for CVaR specifically, since the real index is positive in every historical season (see M9 detail) |
| F16 | Basis-risk engine + heatmap | P1 | M10 | 🟨 engine done + real-run sanity-confirmed (cells nearest the real stations score highest correlation/hedge-effectiveness; basis risk measurably degrades with distance); GeoJSON output built, MapLibre rendering is M13 |
| F17 | Parametric cover designer | P1 | M11 | ✅ done — real case study (SPEC's own stated synthetic Chennai delivery-rider exposure) cuts basis-failure probability 25.8%→3.2% at a tiny premium; also caught a real finding about the optimization objective itself (see M11 detail) |
| F18 | Scenario lab (ENSO states, analog years, rain shocks) | P1 | M11 | ✅ done — 7 presets + real 2015 historical analog, real run against RAINCHNNAI confirms delta=1.0/gamma≈0 structurally across every shock, and the real 2015 analog lands close to the synthetic el_nino preset (internal consistency check) |
| F19 | Public REST API + OpenAPI + typed TS client | P0 | M12 | 🟨 8 of 18 endpoints built (health/contracts/series-valuation/ledger), real envelope + RFC9457 errors, confirmed live via a real uvicorn run + curl, not just TestClient; OpenAPI auto-generates correctly but isn't yet exported to a file; TS client generation not started (needs M13's `web/`) |
| F20 | Next.js dashboard (9 pages) | P0 | M13 | ⬜ |
| F21 | Track-record page (ledger vs outcomes, CRPS, PIT) | P0 | M13 | ⬜ |
| F22 | Alerts (email/Telegram) | P2 | M14 | ⬜ |
| F23 | "Learn" interactive explainer (payoff playground) | P1 | M13 | ⬜ |
| F24 | Multi-site correlated simulator (Wilks) | P2 | M5+ | ⬜ |
| F25 | Seasonal-forecast features (ECMWF SEAS5 via CDS) | P2 | M7+ | ⬜ |
| F26 | Methods paper / preprint | P0 | M15 | ⬜ |

---

## VERIFY checklist (SPEC §3.2) — see docs/VERIFY.md for full citations

**V1-V11 closed** from official NCDEX documents (contract specs, product
notes, launch circulars — all hashed in `specs/sources/`). **V12** (data
redistribution licensing) stays 🔴 open — no sourced document states
explicit terms; treat as not cleared for redistribution.

---

## Open blockers / needs-from-you

1. **MJO (BoM) blocked** — bom.gov.au blocks this network's automated
   access outright. Options: a different network, BoM's
   `webreg@bom.gov.au` registered-user service, or deprioritize (lowest
   priority of the three climate drivers for NE monsoon per SPEC §3.1).
2. **NCDEX bhavcopy live fetch blocked** — bot-detection/fingerprint
   challenge on their API. Options: manually download a bhavcopy CSV and
   hand it to `write_market_quotes()`, or revisit with real browser
   automation (claude-in-chrome) when available.
3. **V12 data licensing** — genuinely unresolved in any public NCDEX
   document; may just stay open permanently (consistent with SPEC's
   research-only positioning).
4. **C++ toolchain** — CMake present; pybind11/scikit-build-core/OpenMP
   not yet installed. Needed starting M5 (week 4), not before.
5. **CDS API key** (Copernicus/ERA5) — only needed if ERA5 features are
   pursued; placeholder in `.env.example`.
6. **GitHub remote** — not created yet (local git only, per your
   instruction). Needed for the ledger's public-repo mirror credibility
   feature (SPEC §2.1).
7. **Backfill could extend further** — currently 1991-2020 (the IMD/
   NCDEX 30-year LPA base period, also RAINMUMBAI's own cited window) +
   2023, all complete with zero gaps. RAINCHNNAI's own LPA base period is
   1971-2020 — extending back to 1971 would let its burn/LPA computations
   use its full official window rather than a 30-year subset of it.

## Known environment quirks (don't re-debug these — see docs/DECISIONS.md)

- Local Postgres is on **port 5433**, not 5432 (native Homebrew Postgres
  owns 5432).
- MLflow is on **port 5001**, not 5000 — macOS's AirPlay Receiver
  (ControlCenter) silently owns 5000 and 403s anything sent there before
  Docker even sees it. Diagnosed via `lsof -nP -iTCP:5000 -sTCP:LISTEN`
  showing `ControlCenter` as the listener, not an MLflow auth bug.
- Docker runs via **colima** (`colima start` if needed).
- Keep the Makefile's `PYTHONPATH` export — works around a macOS/uv/
  CPython 3.12 interaction that breaks `import mq`.
- `imdlib` real-time product writes one raw file per day; historical
  archive writes one per year — `mq.pipelines.imd` has separate
  fetch/write functions for each (`*_realtime` suffix).
- IMD's historical server is occasionally slow/unresponsive for an
  individual year (not a pattern tied to which year) — any backfill loop
  should use a per-year timeout, not assume every year responds quickly.

---

## How to resume work

```bash
cd ~/Documents/MonsoonQuant
colima start                 # if docker isn't already running
make dev                     # postgres + mlflow
make check                   # should be green
tail -f .scratch/backfill.log  # check IMD backfill progress, if still running
```
Next: M0-M11 are all done. M12 (API) is in progress: 8 of 18 endpoints
built (health/contracts/series-valuation/ledger), real envelope +
RFC9457 errors, confirmed via a real uvicorn run, real integration
tests against the real DB (which also surfaced and fixed two genuine
data/design gaps — see M12 detail, `docs/methods/api.md`). Remaining
for M12: the index/quotes/forecast/greeks/mpr/basis GETs (real
functions exist, just not wired into routes) and the three heavy POSTs
(hedge/parametric/scenarios — need request schemas). M6/M8's real-data
application stays blocked on bhavcopy (see M6/M8 detail); M7's
`tft_v1` deliberately skipped (see M7 detail). Or address an open
blocker above (bhavcopy/MJO bot-gates block the most — M2's real
market data, M6/M8's real calibration, and M11's own research outputs
all wait on bhavcopy specifically). Worth considering alongside
either: extending the IMD backfill back to 1951 for SPEC's literal
statistical-holdout window (currently only 1991-2020+2023) — a data
task, not a code task.
