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
| 4 | **M5** Simulator (build) | 🟨 M5.1+M5.2 done (real GLM fit + validated NumPy reference simulator); M5.3 (C++ core) not started | C++ vs NumPy ref agree within 2 SE | CMake, Apple clang (C++20), and libomp are all already present on this machine — no new system installs needed for M5.3. Needs a Philox RNG implementation + pybind11/scikit-build-core wiring + 1951-2020 holdout backfill (currently only have 1991-2020+2023) |
| 5 | **M5** Simulator (validate) · **M6** MPR (start) | ⬜ not started | 1M paths < 10s; seasonal sd ±10% | |
| 6 | **M6** MPR (finish) · **M7** Forecasting (start) | ⬜ not started | λ series w/ CIs live; walk-forward runs | |
| 7 | **M7** Forecasting (finish) | ⬜ not started | CRPSS vs climatology reported | |
| 8 | Buffer | ⬜ not started | — | |
| 9 | **M8** Conditioned pricing · **M9** Greeks | ⬜ not started | 4-method comparison daily; Greek SE < 5% | |
| 10 | **M9** Hedge optimiser | ⬜ not started | `/v1/hedge` < 5s | |
| 11 | **M10** Basis · **M11** Parametric & Scenarios | ⬜ not started | basis heatmap + 1 parametric case study | |
| 12 | **M12** API hardening · live eval | ⬜ not started | contract tests + OpenAPI drift check green | |
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

## M5 detail (simulator — M5.1/M5.2 done, M5.3 C++ core not started)

| Item | Status |
|---|---|
| `mq.pricing.simulator_glm` (M5.1): logistic GLM (p01, p11) + Gamma log-link GLM (amount), on Fourier harmonics + ONI/DMI covariates | ✅ hand-rolled MLE via scipy.optimize (no new statsmodels/sklearn dep) |
| Real fit, nungambakkam station, n=11,323 days (1991-2020+2023) | ✅ both occurrence GLMs + amount GLM converge; amount shape=0.316 (strongly right-skewed, as rainfall is) |
| `mq.pricing.simulator_ref` (M5.2): NumPy reference chain-dependent simulator | ✅ day-by-day Markov occurrence + Gamma amount, accumulates (rain-LPA) deviation exactly like `compute_index` |
| Overdispersion fix (season-level lognormal multiplier on the amount-mean, calibrated via 1-D Brent root-find) | ✅ **real validation**: no-fix simulated seasonal-total sd=272.5mm vs. real historical sd=412.3mm (confirms SPEC's under-dispersion problem on real data); after calibration (sigma=0.336), simulated sd=418.5mm — within SPEC's ±10% acceptance band. Script + log: `.scratch/validate_simulator.py` (gitignored — depends on real backfilled data, not committed as a test, same pattern as the backfill scripts) |
| **M5.3 C++ core (not started)**: CMake + pybind11 + scikit-build-core + OpenMP + Philox4x32-10 | ⬜ toolchain already present (cmake, Apple clang C++20, libomp all pre-installed — confirmed, no brew install needed); not yet wired. Will implement Philox4x32-10 directly (the published Salmon et al. 2011 constants) rather than vendor the full upstream Random123 header tree — simpler, no new external dependency to fetch |
| Statistical holdout validation vs. SPEC's literal "1951-2020" window | ⬜ **blocked on data, not code** — current backfill is 1991-2020+2023 only; extending back to 1951 needs another IMD backfill run (same pattern as the existing one, just more years) |
| `make bench` (1M paths × 92 days < 10s) | ⬜ needs the C++ core to exist first |

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
| F11 | Market price of risk (Wang + Esscher) w/ bootstrap/Bayesian CIs | P0 | M6 | ⬜ |
| F12 | Probabilistic forecaster (climatology → analog → LightGBM-quantile + conformal) | P0 | M7 | 🟨 clim_v1 (rung 1) done |
| F13 | Forecast-conditioned pricing & fair-value band | P0 | M8 | ⬜ |
| F14 | Rainfall Greeks (delta, gamma, theta) with common random numbers | P0 | M9 | ⬜ |
| F15 | Hedge optimiser (min-variance + CVaR, integer lots, caps, margin) | P0 | M9 | ⬜ |
| F16 | Basis-risk engine + heatmap | P1 | M10 | ⬜ |
| F17 | Parametric cover designer | P1 | M11 | ⬜ |
| F18 | Scenario lab (ENSO states, analog years, rain shocks) | P1 | M11 | ⬜ |
| F19 | Public REST API + OpenAPI + typed TS client | P0 | M12 | ⬜ |
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
Next: M4 is complete; M5.1 (GLM fitting) and M5.2 (NumPy reference
simulator, overdispersion fix validated on real data) are complete.
M5.3 (C++ core) is next: toolchain is already present (cmake, clang
C++20, libomp), needs pybind11/scikit-build-core wiring + a Philox4x32-10
implementation + parity tests vs. the now-working NumPy reference. Also
consider extending the IMD backfill back to 1951 for SPEC's literal
holdout validation window (currently only 1991-2020+2023). Or address
an open blocker above.
