# MonsoonQuant — Status: what's done, what's left

Source of truth: `docs/SPEC.md`. This file is the single tracking sheet —
update it at the end of every milestone (alongside a `docs/PROGRESS.md`
entry). Status legend: ✅ done · 🟨 in progress · ⬜ not started.

Repo: `~/Documents/MonsoonQuant` (local git, not yet pushed anywhere).

---

## Milestones (SPEC §13 — 15-week plan, Mon 5 Oct 2026 → Sun 17 Jan 2027)

| Week | Milestone | Status | Gate | Notes |
|---|---|---|---|---|
| 1 | **M0** Scaffold | ✅ done | `make check` green | repo, uv, Makefile, pre-commit, CI skeleton, docker-compose, `mq` CLI, settings, structlog, as_of io layer + test, Alembic + ledger trigger — all verified against a live Postgres |
| 1 | **M1** Specs + ledger live | 🟨 mostly done | ledger ≥ 1 verified daily row/contract; `mq ledger verify` passes | **Gate met for RAINCHNNAI** (real row written + verified). RAINMUMBAI deferred — its proxy season isn't open today (see below). Contract specs still DRAFT — **blocked on you** for the official NCDEX PDFs (V1–V12, docs/VERIFY.md) |
| 2 | **M2** Market data & DQ | ⬜ not started | DQ gate blocks on bad data | DQ01-DQ04 (generic) already built in M1.3; DQ05-DQ10 (market-data specific) still open |
| 2 | **M3** Index engine | ⬜ not started | index reproducible for any past date | |
| 3 | **M4** Burn & distribution pricing | ⬜ not started | 2 independent P-measure prices + methods note | |
| 4 | **M5** Simulator (build) | ⬜ not started | C++ vs NumPy ref agree within 2 SE | needs CMake/pybind11/OpenMP toolchain — not yet installed |
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

| Item | Status |
|---|---|
| Repo layout (SPEC §5) | ✅ |
| git init (local only, no remote) | ✅ |
| uv workspace, Python 3.12, `pyproject.toml` | ✅ |
| Makefile (`bootstrap/check/test-golden/bench/ingest/reproduce/dev/down`) | ✅ (`ingest`/`reproduce` are forward stubs — no `mq run daily` / `mq research reproduce` yet) |
| pre-commit (ruff, mypy via local uv-env hook, gitleaks; clang-format once `core/` exists) | ✅ installed, `run --all-files` passes |
| CI skeleton (`.github/workflows/ci.yml`) | ✅ written; not yet run on a real push/PR; web + C++ jobs commented as TODO |
| docker-compose (postgres:16 on **5433**, mlflow) | ✅ both up locally via colima |
| `mq` CLI (Typer) | ✅ |
| Settings (pydantic-settings) + structlog | ✅ |
| `mq.io.asof` as_of-aware layer + look-ahead test | ✅ |
| Alembic migrations — all 11 §6.1 tables | ✅ applied to live Postgres |
| `prediction_ledger` immutability trigger | ✅ UPDATE/DELETE proven blocked at the DB level |
| `CLAUDE.md`, `docs/{PROGRESS,DECISIONS,VERIFY,STATUS}.md` | ✅ |

---

## M1 detail (done this session)

| Item | Status |
|---|---|
| Source register (`mq.specs.sources`, `mq sources add`/`list`) | ✅ SHA-256 content-addressed, immutable, DB + YAML sidecar |
| `ContractSpec` model (`mq.specs.contract`) + loader (`mq.specs.loader`) | ✅ `TODO_VERIFY` sentinel per-field; loader rejects drafts unless `--allow-draft` |
| DRAFT YAMLs for RAINCHNNAI & RAINMUMBAI | ✅ `specs/contracts/{code}/2026-10-04-draft.yaml`, all VERIFY-dependent fields marked `TODO_VERIFY` |
| `mq specs validate` CLI | ✅ |
| DQ01–DQ04 gate (`mq.pipelines.dq`) | ✅ generic, reusable; persists to `dq_results` |
| IMD 0.25° gridded rainfall ingestion (`mq.pipelines.imd`) | ✅ historical (`imdlib.get_data`) + **near-real-time** (`imdlib.get_real_data`) paths, both DQ-gated |
| ONI / DMI ingestion (`mq.pipelines.climate_idx`) | ✅ **live data fetched**: ONI 920 rows (1950–2026), DMI 1877 rows (1870–2026), both through the DQ gate, written to Parquet |
| MJO ingestion | 🟨 parser implemented & unit-tested against a real-format fixture; **live fetch blocked** — BoM blocks this network's automated access outright (not just a header issue — their own help page returns the same block). Not worked around; needs either a different network path or BoM's registered-user service |
| `clim_v1` climatology forecaster (`mq.forecasting.climatology`) | ✅ |
| Ledger hash chain (`mq.ledger.hashing`), writer (`mq.ledger.writer`), verify (`mq.ledger.verify`) | ✅ idempotent writes, tamper detection proven (deliberately-corrupted row caught by `mq ledger verify`) |
| `mq ledger verify` / `mq ledger export` CLI | ✅ |
| **Real ledger row written and verified**: RAINCHNNAI, `clim_v1`, as_of 2026-10-04 | ✅ exported to `ledger/2026/10/04.jsonl` |
| Daily export → public GitHub repo + Actions cron | ⬜ **deferred** — no GitHub remote configured yet (local git only, per your earlier instruction) |
| RAINMUMBAI ledger row | ⬜ **deferred** — see note below |

### Why RAINMUMBAI has no ledger row yet
`clim_v1` needs a (period_start, period_end) window. Until VERIFY V3 is
closed, this project is using *proxy* windows for research purposes only
(clearly labelled, never presented as the real contract terms): Chennai's
NE monsoon (Oct 1–Dec 31, stated directly in SPEC §2) and Mumbai's SW
monsoon (Jun 1–Sep 30, general meteorological knowledge, not from the
SPEC). As of today (Oct 4), Chennai's proxy window is open — Mumbai's
closed on Sep 30. Writing a "remaining rain" forecast for a season that's
already over doesn't mean anything, so it's skipped rather than faked.
Revisit either when VERIFY V3 resolves the real contract periods, or when
the Jun 2027 proxy window opens.

### Honesty note on the one real ledger row
It's a climatology sample of **n=1** (only 2023's IMD data has been
ingested — see "IMD backfill scope" below) and uses a PROXY grid cell
nearest Chennai, not an official station/index per VERIFY V2/V3. The
quantiles are therefore a single degenerate point, not a real
distribution. This is intentionally transparent in `data_version` (tagged
`imd-2023-only-n1`) and should not be read as a real forecast — it proves
the ledger mechanics (hash chain, append-only, idempotency, export) work
end-to-end on real data, which was the actual goal of getting this live in
Week 1 per SPEC §2's "Critical Timing Insight". A real climatology needs a
real backfill (see below).

---

## Feature catalogue (SPEC §1.4)

| ID | Feature | Pri | Milestone | Status |
|---|---|---|---|---|
| F01 | Versioned contract-spec registry (YAML + source PDFs + hashes) | P0 | M1 | 🟨 register + model + loader + DRAFT YAMLs done; real PDFs still needed |
| F02 | Market-data ingestion (settlement, volume, OI) with provenance | P0 | M2 | ⬜ |
| F03 | Gridded rainfall ingestion (IMD 0.25°) + station mapping | P0 | M2 | 🟨 ingestion done (historical + realtime); station mapping blocked on VERIFY V2 |
| F04 | Climate drivers (ONI, DMI/IOD, MJO phase) | P0 | M2 | 🟨 ONI+DMI live; MJO coded but fetch-blocked (BoM) |
| F05 | Data-quality gate blocking publication | P0 | M2 | 🟨 DQ01-DQ04 done; DQ05-DQ10 (market data) pending |
| F06 | Index replication engine + proxy-error tracking | P0 | M3 | ⬜ |
| F07 | **Prediction Ledger** (append-only, hash-chained, public) | P0 | M1→ | 🟨 fully working locally (writer/verify/export + 1 real row); public GitHub mirror deferred (no remote) |
| F08 | Historical burn analysis (with detrending options) | P0 | M4 | ⬜ |
| F09 | Index-distribution pricing (Gamma/Lognormal/KDE/bootstrap/ENSO-conditioned) | P0 | M4 | ⬜ |
| F10 | C++ chain-dependent stochastic rainfall simulator (1M paths < 10s) | P0 | M5 | ⬜ |
| F11 | Market price of risk (Wang + Esscher) w/ bootstrap/Bayesian CIs | P0 | M6 | ⬜ |
| F12 | Probabilistic forecaster (climatology → analog → LightGBM-quantile + conformal) | P0 | M7 | 🟨 clim_v1 (rung 1 of the ladder) done |
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

## VERIFY checklist (SPEC §3.2) — see docs/VERIFY.md for detail

All 12 items (V1–V12) are still 🔴 **open** — none can be closed without
the official NCDEX contract-specification PDFs. `ContractSpec` YAMLs exist
as DRAFTs (`--allow-draft` required to load them) with every
VERIFY-dependent field marked `TODO_VERIFY`.

---

## Open blockers / needs-from-you

1. **Official contract specs** — download NCDEX spec PDFs for RAINCHNNAI
   and RAINMUMBAI so VERIFY V1–V12 can be closed.
2. **IMD historical backfill scope** — only 2023 is ingested (1 year, by
   your explicit choice, as a pipeline smoke test). `clim_v1`'s one real
   ledger row is therefore a degenerate n=1 "climatology". A real
   climatology needs a real backfill (`mq run backfill`, not yet a CLI
   command — direct calls to `write_rain_grid_year` work today). This is a
   deliberate, separate decision due to data volume (~24MB/year — a few
   GB for a multi-decade backfill) and download time; tell me how many
   years you want when ready.
3. **MJO (BoM) blocked** — this network's automated access to
   bom.gov.au is blocked outright (confirmed even on their own help page,
   not just the data URL). Options: a different network, BoM's
   `webreg@bom.gov.au` registered-user service, or skip MJO (it's one of
   three climate drivers and the lowest-priority of the three for NE
   monsoon per SPEC §3.1).
4. **C++ toolchain** — CMake is present; `pybind11`/`scikit-build-core`/
   OpenMP not yet installed or exercised. Needed starting M5 (week 4).
5. **CDS API key** (Copernicus, for ERA5/SEAS5) — only needed if ERA5
   features are pursued; `MQ_CDS_API_KEY` placeholder is in `.env.example`.
6. **GitHub remote** — not created yet (local git only, per your
   instruction). Needed for the ledger's public-repo mirror + Actions cron
   (SPEC §2.1's "git timestamp is independent proof" credibility feature).

## Known environment quirks (don't re-debug these — see docs/DECISIONS.md)

- Local Postgres is on **port 5433**, not 5432 (a native Homebrew Postgres
  already owns 5432 on this machine).
- Docker runs via **colima** (`colima start` if `docker compose` can't
  reach the daemon).
- Always let the Makefile's `PYTHONPATH` export do its job — don't remove
  it; it works around a macOS-only `uv`/CPython 3.12 interaction that
  breaks `import mq`.
- `imdlib`'s real-time product writes one raw file per day
  (`rain_ind0.25_YY_MM_DD.grd`) vs. the historical archive's one-per-year
  (`rain/<year>.grd`) — `mq.pipelines.imd` has separate fetch/write
  functions for each (`*_realtime` suffix).

---

## How to resume work

```bash
cd ~/Documents/MonsoonQuant
colima start                 # if docker isn't already running
make dev                     # postgres + mlflow
make check                   # should be green (45 tests as of this entry)
```
Next: either supply the NCDEX PDFs (unblocks real VERIFY closure), decide
the IMD backfill scope (unblocks a real climatology), or move ahead to M2
(market data ingestion + DQ05-DQ10) with the current DRAFT specs.
