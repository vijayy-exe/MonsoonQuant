# MonsoonQuant — Master Build Specification

> **Prices, forecasts, explains and hedges India's exchange-traded rainfall futures (RAINCHNNAI, RAINMUMBAI).**
> A small, auditable quant-research platform — not a folder of notebooks.

| Item | Value |
|---|---|
| Owner | Vijay BS |
| Build window | Mon 5 Oct 2026 → Sun 17 Jan 2027 (15 weeks) |
| Positioning | Open research & analytics platform. **Not** trading advice. |
| Core stack | Python 3.12 (uv) · C++20 + pybind11 · FastAPI · Next.js 15 · PostgreSQL 16 · Parquet + DuckDB · MLflow · Docker |
| Spec version | 2.0 (supersedes `MonsoonQuant_Full_Implementation_Plan.md` v1) |

---

## 0. READ FIRST — Operating Manual

This file is the single source of truth. Read it fully before writing code and re-read the relevant section before starting each milestone.

### 0.1 Your role
You are the lead engineer on a quantitative-finance research platform. Correctness, reproducibility and honest uncertainty beat feature count. When the spec and reality disagree (e.g., an official contract document says something different), **reality wins — stop, record it in `docs/DECISIONS.md`, and ask the owner.**

### 0.2 Work loop (every task)
1. **Plan** — state the milestone/task ID (e.g., `M3.2`), files to touch, and the acceptance check. Use plan mode for anything touching >3 files.
2. **Test first** for all maths (index, payoff, pricing, MPR, Greeks, hedge, CVaR, basis). Write the failing test, then the code.
3. **Implement** the smallest change that passes.
4. **Verify** — run `make check` (lint + types + tests). Never claim a task is done without running it.
5. **Log** — append a 2–4 line entry to `docs/PROGRESS.md` (date, task ID, what changed, measured numbers).
6. **Commit** — Conventional Commits (`feat(pricing): add Wang transform calibration`). One logical change per commit.

### 0.3 Stop-and-ask triggers (do NOT guess)
- Any contract-specification detail marked **`VERIFY`** in §3.
- A golden test fails and the fix would mean changing the expected value.
- A data source's licence, schema or URL changed.
- A result looks "too good" (e.g., forecast skill > 30% over climatology, hedge effectiveness > 95%) — assume leakage until proven otherwise.
- Adding any new paid service or dependency > 50 MB.

### 0.4 Hard rules (never violate)
1. Financial numbers come only from the pricing/risk engines. LLMs (if ever added) only explain.
2. Every published number carries `data_version`, `model_version`, `spec_version`, `as_of`.
3. No look-ahead: every feature, fit and forecast is computed with data available **at the issue timestamp**. Enforced by `as_of` filtering in the data access layer, not by discipline.
4. Raw files are immutable (content-addressed by SHA-256). Never overwrite, never edit.
5. Forecasts are written to the append-only **Prediction Ledger** (§2) *before* outcomes are known.
6. Synthetic data and synthetic exposures are labelled `synthetic=true` everywhere, including the UI.
7. Uncertainty intervals are shown next to every point estimate.
8. No secrets in the repo. `.env.example` only.
9. Reproducible from a clean checkout: `make bootstrap && make reproduce` regenerates every research figure.

### 0.5 Standard commands (create these in M0)
```bash
make bootstrap     # uv sync, pnpm install, build C++ ext, pre-commit install
make check         # ruff, ruff format --check, mypy --strict (core pkgs), clang-format check, pytest -q
make test-golden   # golden tests only
make bench         # 1M-path simulator benchmark -> docs/benchmarks/
make ingest        # run all ingestion pipelines for today
make reproduce     # rebuild all research artifacts from raw data
make dev           # docker compose up (db, api, web, mlflow)
mq --help          # project CLI (Typer)
```

### 0.6 Files to maintain
| File | Purpose |
|---|---|
| `AGENTS.md` | Short (≤150 lines) extract of §0 + current milestone. Template in Appendix A. |
| `docs/PROGRESS.md` | Running log with measured numbers. |
| `docs/DECISIONS.md` | ADR-lite: decision, alternatives, reason, date. |
| `docs/VERIFY.md` | Open questions about contract specs/data; each closed with a source link + SHA. |
| `docs/methods/*.md` | One methods note per engine (feeds the paper). |

---

## 1. Product Definition

### 1.1 Questions the platform answers
1. What is the rainfall index **right now**, and how well does our proxy replicate the official one?
2. What is the contract worth under four independent pricing approaches (burn, distribution, stochastic, forecast-conditioned)?
3. How wide is the fair-value band, and why?
4. What is the **market-implied price of rainfall risk** (λ), with honest confidence intervals?
5. How does value respond to more rain (delta) and time passing (theta)?
6. How many lots should a weather-exposed business hold, and how much risk is left (variance, CVaR, basis)?
7. Could the same machinery design a parametric cover for a delivery rider or farmer?
8. Was our forecast right? (public, timestamped track record)

### 1.2 Users
| Persona | Need | Primary pages |
|---|---|---|
| Quant / researcher | Methods, MPR, reproducibility | Pricing, Research, API |
| Risk manager at an exposed business | Hedge sizing, basis risk | Hedge, Basis |
| Student / journalist | Understand rainfall derivatives | Learn, Overview |
| Admissions / recruiter | Evidence of rigour | Track Record, Methods, GitHub |

### 1.3 Non-goals
- No order routing, no broker integration, no buy/sell signals, no "you should trade" language.
- No personalised advice. Hedge outputs are labelled **"model-generated hedge quantities for a stated exposure"**.
- No claim that λ is a stable structural premium from a short sample.

### 1.4 Feature catalogue (priority-tagged)
P0 = must ship, P1 = should ship, P2 = stretch. **MVP cut line = all P0.**

| ID | Feature | Pri | Milestone |
|---|---|---|---|
| F01 | Versioned contract-spec registry (YAML + source PDFs + hashes) | P0 | M1 |
| F02 | Market-data ingestion (settlement, volume, OI) with provenance | P0 | M2 |
| F03 | Gridded rainfall ingestion (IMD 0.25°) + station mapping | P0 | M2 |
| F04 | Climate drivers (ONI, DMI/IOD, MJO phase) | P0 | M2 |
| F05 | Data-quality gate blocking publication | P0 | M2 |
| F06 | Index replication engine + proxy-error tracking | P0 | M3 |
| F07 | **Prediction Ledger** (append-only, hash-chained, public) | P0 | M1→ |
| F08 | Historical burn analysis (with detrending options) | P0 | M4 |
| F09 | Index-distribution pricing (Gamma, Lognormal, KDE, bootstrap, ENSO-conditioned) | P0 | M4 |
| F10 | C++ chain-dependent stochastic rainfall simulator (1M paths < 10 s) | P0 | M5 |
| F11 | Market price of risk (Wang + Esscher) with bootstrap/Bayesian CIs | P0 | M6 |
| F12 | Probabilistic forecaster (climatology → analog → LightGBM-quantile + conformal) | P0 | M7 |
| F13 | Forecast-conditioned pricing & fair-value band | P0 | M8 |
| F14 | Rainfall Greeks (delta, gamma, theta) with common random numbers | P0 | M9 |
| F15 | Hedge optimiser (min-variance + CVaR, integer lots, caps, margin) | P0 | M9 |
| F16 | Basis-risk engine + heatmap | P1 | M10 |
| F17 | Parametric cover designer | P1 | M11 |
| F18 | Scenario lab (ENSO states, analog years, rain shocks) | P1 | M11 |
| F19 | Public REST API + OpenAPI + typed TS client | P0 | M12 |
| F20 | Next.js dashboard (7 pages) | P0 | M13 |
| F21 | Track-record page (ledger vs outcomes, CRPS, PIT) | P0 | M13 |
| F22 | Alerts (email/Telegram) | P2 | M14 |
| F23 | "Learn" interactive explainer (payoff playground) | P1 | M13 |
| F24 | Multi-site correlated simulator (Wilks) | P2 | M5+ |
| F25 | Seasonal-forecast features (ECMWF SEAS5 via CDS) | P2 | M7+ |
| F26 | Methods paper / preprint | P0 | M15 |

---

## 2. Critical Timing Insight — Start the Prediction Ledger in Week 1

Chennai's **northeast monsoon runs roughly October–December** — it is happening *during* this build. The v1 plan put live evaluation in week 12, by which time the season is nearly over. Fix:

- **Week 1:** ingestion + a climatology-only forecaster + the ledger go live. Every day, write a forecast of the remaining-season index distribution for each live contract.
- **Weeks 4–9:** better models are added as **new model IDs**; they never overwrite earlier ledger rows.
- **Week 12–13:** evaluate *every* model on genuinely out-of-sample data (CRPS, PIT histogram, coverage).

### 2.1 Ledger design
```sql
CREATE TABLE prediction_ledger (
  id              BIGSERIAL PRIMARY KEY,
  issued_at       TIMESTAMPTZ NOT NULL,          -- wall-clock at write time
  as_of_date      DATE        NOT NULL,          -- information cutoff
  contract_code   TEXT        NOT NULL,
  model_id        TEXT        NOT NULL,          -- e.g. clim_v1, lgbm_q_v2
  model_version   TEXT        NOT NULL,
  data_version    TEXT        NOT NULL,
  target          TEXT        NOT NULL,          -- 'final_index' | 'remaining_rain_mm'
  quantiles       JSONB       NOT NULL,          -- {"0.05":..,"0.25":..,"0.5":..,...}
  fair_value      NUMERIC,
  fair_value_lo90 NUMERIC,
  fair_value_hi90 NUMERIC,
  payload_sha256  TEXT        NOT NULL,
  prev_hash       TEXT        NOT NULL,          -- hash chain
  row_hash        TEXT        NOT NULL UNIQUE
);
-- No UPDATE/DELETE: enforce with a trigger that raises an exception.
```
- `row_hash = sha256(prev_hash || canonical_json(row_without_hashes))`.
- A daily job exports the day's rows to `ledger/YYYY/MM/DD.jsonl` and commits them to a **public GitHub repo** (`monsoonquant-ledger`). The git timestamp is independent proof the forecast predates the outcome.
- `mq ledger verify` recomputes the chain and fails loudly on any break.

This single feature is the strongest credibility signal in the whole project.

---

## 3. Domain Primer & VERIFY List

### 3.1 Domain rules to get right
- **Futures pricing:** with daily mark-to-market, the futures price is a martingale under the pricing measure Q: `F_t = E_Q[ I_T · multiplier | 𝓕_t ]`. **No discounting** of the futures price itself. (Discounting applies to option-like payoffs in the parametric designer.)
- **Index is path-dependent on cumulative rainfall:** value at time t = function of (rain observed so far) + distribution of (rain still to come). Every engine must take `observed_to_date` as an explicit input.
- **Thin market:** settlement prices may be exchange-determined with few or zero trades. Store volume/OI next to every price and weight MPR calibration by liquidity; exclude zero-volume days from headline λ (report them separately).
- **Chain-dependent rainfall models under-disperse seasonal totals** (the "overdispersion problem"). The simulator must be validated on *seasonal-total variance*, not only daily statistics; fix with ENSO/IOD covariates or parameter uncertainty (§7.4).
- **Basis risk is the product's honesty test:** a contract indexed to 1–2 stations rarely matches a business's local rainfall.

### 3.2 VERIFY — must be closed from official sources in M1 (do not invent)
Record each answer in the spec YAML with `source_id`, page number and quoted clause in `docs/VERIFY.md`.

| # | Question | Why it matters |
|---|---|---|
| V1 | Exact contract codes, listing date, active months/expiries | Contract calendar |
| V2 | Stations / grid cells and how they are combined (mean? weighted?) | Index engine |
| V3 | Index definition: cumulative rain vs cumulative deviation; mm vs % of LPA; daily or period | Payoff |
| V4 | LPA source, base period and values per day/period | Index engine |
| V5 | Data provider for settlement (IMD? which product? revision policy) | Proxy vs official |
| V6 | Contract multiplier / lot size / tick size / price unit | Lots, P&L |
| V7 | Daily price limits, position limits, order-size caps | Hedge constraints |
| V8 | Margin (initial, ELM, special) | Hedge constraints |
| V9 | Final settlement procedure and timing | Expiry handling |
| V10 | Treatment of missing station data | Index robustness |
| V11 | Whether products are actively traded, suspended or relaunched | Scope / fallbacks |
| V12 | Data licensing for NCDEX price data and IMD data | Public redistribution |

If V11 shows the contracts are not trading, switch to **Fallback Mode B** (§17).

### 3.3 Data sources (verify licences in M1)
| Data | Source | Access | Notes |
|---|---|---|---|
| Gridded daily rainfall 0.25°, 1901– | IMD Pune | `imdlib` Python package | Primary history; ~1–2 day lag for real-time product |
| Station data | IMD / Chennai RMC bulletins | Manual / PDF parse | For proxy validation |
| Reanalysis | ERA5 (Copernicus CDS) | `cdsapi` (new CDS API key format) | Humidity, winds, SST features |
| Satellite precip (backup) | CHIRPS / GPM IMERG | HTTP | Gap-filling, sanity check |
| ONI | NOAA CPC | Text file | Monthly |
| DMI (IOD) | NOAA PSL | Text file | Weekly/monthly |
| MJO RMM | BoM | Text file | Daily; relevant for NE monsoon bursts |
| Seasonal forecast (P2) | ECMWF SEAS5 via CDS | `cdsapi` | Ensemble features |
| Futures prices | NCDEX bhavcopy / contract pages | Downloader | Check robots/ToS |

---

## 4. Architecture

```text
 ┌──────────── External ────────────┐
 │ IMD · ERA5 · CHIRPS · ONI · DMI  │
 │ MJO · NCDEX bhavcopy · spec PDFs │
 └───────────────┬──────────────────┘
                 ▼
 ┌──────── Ingestion (pipelines/) ──────────┐
 │ fetch → raw (immutable, SHA-256)          │
 │ → validate (pandera) → normalise          │
 │ → DQ gate ──fail──▶ alert, block publish  │
 └───────────────┬──────────────────────────┘
                 ▼
 ┌──────── Storage ─────────────────────────┐
 │ Postgres: metadata, quotes, ledger, runs │
 │ Parquet (+DuckDB): gridded rain, features│
 │ Object store: raw files, model artifacts │
 └──────┬──────────────┬───────────────────┘
        ▼              ▼
 ┌─ Index engine ─┐ ┌─ Forecast engine ─────────┐
 │ proxy, official│ │ clim → analog → LGBM-q    │
 │ proxy error    │ │ + conformal calibration   │
 └──────┬─────────┘ └──────┬───────────────────┘
        └───────┬──────────┘
                ▼
 ┌──────── Pricing engine ──────────────────┐
 │ burn · distribution · C++ MC simulator   │
 │ forecast-conditioned · Q-measure (MPR)   │
 └───────────────┬──────────────────────────┘
                 ▼
 ┌──────── Risk engine ─────────────────────┐
 │ Greeks · hedge (MV/CVaR) · basis ·       │
 │ parametric designer · scenarios          │
 └───────────────┬──────────────────────────┘
                 ▼
     Prediction Ledger  ──▶ public git repo
                 ▼
          FastAPI (/v1)  ──▶ Next.js dashboard
```

### 4.1 Tech choices (locked unless an ADR changes them)
| Concern | Choice | Reason |
|---|---|---|
| Python env | `uv`, Python 3.12 | Fast, lockfile |
| Dataframes | Polars (pipelines), pandas only where libs require | Speed, strict types |
| Validation | Pydantic v2 (configs/API), pandera (dataframes) | Typed contracts |
| Analytics store | Parquet partitioned by `source/year/month` + DuckDB | Cheap, fast, local-first |
| DB | PostgreSQL 16 + SQLAlchemy 2 + Alembic | Ledger, metadata |
| C++ build | CMake + scikit-build-core + pybind11, C++20, OpenMP | Clean wheel build |
| RNG | Counter-based Philox4x32-10 (Random123 header) | Reproducible parallel streams |
| Stats/opt | SciPy, statsmodels, cvxpy + HiGHS | GLMs, LP/MILP |
| ML | LightGBM, scikit-learn, `mapie` (conformal), `scoringrules` (CRPS) | Small-data friendly |
| Experiments | MLflow (local file store → S3 later) | Model registry |
| CLI | Typer (`mq`) | One entry point |
| Scheduling | GitHub Actions cron (MVP) → AWS EventBridge (P2) | Free first |
| API | FastAPI, orjson, slowapi rate limit | Typed, fast |
| Web | Next.js 15 App Router, TypeScript, Tailwind, shadcn/ui, ECharts, MapLibre, TanStack Query, `openapi-typescript` | Typed client from OpenAPI |
| Observability | structlog JSON logs, Sentry, Prometheus `/metrics` | |
| Hosting (budget) | Vercel (web) · Fly.io/Render (API) · Neon (Postgres) · Cloudflare R2 (objects) | ~₹0–1,500/month |
| Hosting (AWS path) | ECS Fargate · RDS · S3 · EventBridge · Terraform | If credits available |

---

## 5. Repository Layout

```text
monsoonquant/
├── AGENTS.md                     # Appendix A
├── README.md                     # pitch, screenshots, quickstart, results table
├── Makefile
├── pyproject.toml / uv.lock      # workspace
├── docker-compose.yml            # postgres, api, web, mlflow
├── .github/workflows/            # ci.yml, ingest-daily.yml, ledger-export.yml, bench.yml
├── specs/
│   ├── contracts/RAINCHNNAI/2026-xx-xx.yaml
│   ├── contracts/RAINMUMBAI/2026-xx-xx.yaml
│   └── sources/                  # source register (YAML) — PDFs live in object store
├── core/                         # C++ simulator
│   ├── CMakeLists.txt
│   ├── include/mq/{rng.hpp,params.hpp,simulate.hpp,payoff.hpp}
│   ├── src/
│   ├── bindings/module.cpp
│   └── tests/                    # Catch2
├── src/mq/
│   ├── config.py                 # settings (pydantic-settings)
│   ├── versioning.py             # data/model/spec version hashing
│   ├── db/                       # models.py, session.py, migrations/
│   ├── io/                       # as_of-aware readers (THE ONLY way to read data)
│   ├── specs/                    # ContractSpec pydantic model + loader
│   ├── pipelines/{imd,era5,chirps,climate_idx,ncdex,dq}.py
│   ├── index/{engine.py,proxy.py,lpa.py}
│   ├── pricing/{burn.py,distribution.py,simulator.py,conditioned.py,measure.py}
│   ├── mpr/{wang.py,esscher.py,calibrate.py,uncertainty.py}
│   ├── forecasting/{features.py,climatology.py,analog.py,lgbm_quantile.py,conformal.py,evaluate.py}
│   ├── risk/{greeks.py,hedge.py,cvar.py,basis.py,parametric.py,scenarios.py}
│   ├── ledger/{writer.py,verify.py,export.py}
│   ├── api/{main.py,deps.py,schemas/,routes/}
│   └── cli.py
├── web/                          # Next.js app
├── tests/{unit,golden,property,statistical,integration,e2e}/
├── notebooks/                    # exploratory only; never imported by src
├── research/                     # reproducible scripts → figures/ tables/
├── paper/                        # LaTeX/Markdown preprint
└── docs/{PROGRESS.md,DECISIONS.md,VERIFY.md,methods/,benchmarks/,data_dictionary.md}
```

**Rule:** notebooks may import `mq`; `mq` never imports notebooks. Any figure in the paper is produced by a script in `research/`.

---

## 6. Data Model

### 6.1 Postgres (core tables)
```sql
CREATE TABLE sources (
  source_id      TEXT PRIMARY KEY,           -- 'ncdex_spec_rainchnnai_2026'
  title TEXT, publisher TEXT, url TEXT,
  published_at DATE, effective_at DATE,
  downloaded_at TIMESTAMPTZ NOT NULL,
  sha256 TEXT NOT NULL, object_key TEXT NOT NULL, licence TEXT
);

CREATE TABLE raw_files (
  sha256 TEXT PRIMARY KEY, source_name TEXT NOT NULL, url TEXT,
  fetched_at TIMESTAMPTZ NOT NULL, bytes BIGINT, object_key TEXT NOT NULL
);

CREATE TABLE contract_specs (
  contract_code TEXT, spec_version TEXT, yaml JSONB NOT NULL,
  source_ids TEXT[] NOT NULL, PRIMARY KEY (contract_code, spec_version)
);

CREATE TABLE contracts (                        -- listed series
  series_id TEXT PRIMARY KEY,                   -- 'RAINCHNNAI-DEC26'
  contract_code TEXT, spec_version TEXT,
  period_start DATE, period_end DATE, expiry DATE, status TEXT
);

CREATE TABLE market_quotes (
  series_id TEXT, trade_date DATE, open NUMERIC, high NUMERIC, low NUMERIC,
  close NUMERIC, settle NUMERIC, volume BIGINT, open_interest BIGINT,
  raw_sha256 TEXT REFERENCES raw_files, ingested_at TIMESTAMPTZ,
  PRIMARY KEY (series_id, trade_date)
);

CREATE TABLE index_values (
  series_id TEXT, obs_date DATE, as_of_date DATE,
  proxy_value NUMERIC, official_value NUMERIC,
  abs_error NUMERIC, pct_lpa_error NUMERIC, data_version TEXT,
  PRIMARY KEY (series_id, obs_date, as_of_date)
);

CREATE TABLE model_runs (
  run_id UUID PRIMARY KEY, kind TEXT, model_id TEXT, model_version TEXT,
  data_version TEXT, spec_version TEXT, params JSONB, metrics JSONB,
  started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, git_sha TEXT, mlflow_run TEXT
);

CREATE TABLE valuations (
  series_id TEXT, as_of_date DATE, method TEXT,          -- burn|dist|mc|cond
  measure TEXT,                                          -- P | Q_wang | Q_esscher
  fair_value NUMERIC, lo90 NUMERIC, hi90 NUMERIC, n_paths INT,
  run_id UUID REFERENCES model_runs,
  PRIMARY KEY (series_id, as_of_date, method, measure)
);

CREATE TABLE mpr_estimates (
  series_id TEXT, as_of_date DATE, transform TEXT,       -- wang|esscher
  lambda NUMERIC, ci_lo NUMERIC, ci_hi NUMERIC, method_ci TEXT,
  days_to_expiry INT, volume BIGINT, open_interest BIGINT, n_obs INT,
  run_id UUID REFERENCES model_runs,
  PRIMARY KEY (series_id, as_of_date, transform)
);

CREATE TABLE dq_results (
  check_id TEXT, dataset TEXT, run_at TIMESTAMPTZ, status TEXT, -- pass|warn|fail
  details JSONB
);
-- plus prediction_ledger (§2.1), alerts, api_keys (hashed)
```

### 6.2 Parquet datasets
| Dataset | Partition | Columns |
|---|---|---|
| `rain_grid` | `source=imd/year=` | date, lat, lon, rain_mm, product_version, raw_sha256 |
| `rain_station` | `station=/year=` | date, station_id, rain_mm, flag |
| `era5_daily` | `var=/year=` | date, lat, lon, value |
| `climate_idx` | `index=` | date, value, release_date |
| `features` | `contract=/as_of_year=` | as_of_date, feature columns, feature_version |

`release_date` is mandatory for every climate index row — features use the value **released** by `as_of`, not the value for that month (ONI is published with a lag and revised).

### 6.3 Versioning
- `data_version = sha256(sorted(raw_sha256s used)) [:12]`
- `model_version = semver + git_sha[:7]`
- `spec_version = effective date of the contract-spec YAML`
- `mq version show <series_id> <date>` prints the full lineage for any number on the dashboard.

---

## 7. Engine Specifications

### 7.1 Contract spec model (`mq.specs`)
```python
class StationRef(BaseModel):
    station_id: str; name: str; lat: float; lon: float
    grid_cell: tuple[float, float] | None   # nearest IMD 0.25° cell
    weight: float = 1.0

class IndexDef(BaseModel):
    kind: Literal["cumulative_rain_mm", "cumulative_deviation_pct_lpa", "cumulative_deviation_mm"]
    aggregation: Literal["mean", "weighted_mean"]
    lpa: LPARef                      # source_id + base period + table
    period_start: MonthDay; period_end: MonthDay
    missing_data_rule: str           # VERIFY V10

class ContractSpec(BaseModel):
    contract_code: str; spec_version: date
    stations: list[StationRef]; index: IndexDef
    multiplier_inr_per_point: Decimal      # VERIFY V6
    tick_size: Decimal; lot_size: int
    max_order_lots: int | None; position_limit_lots: int | None
    margin_pct: Decimal | None
    settlement: SettlementRule
    source_ids: list[str]
```
Loader rejects any spec with an unresolved `VERIFY` field unless `--allow-draft`.

### 7.2 Index engine (`mq.index`)
```python
def compute_index(spec: ContractSpec, rain: pl.DataFrame, as_of: date) -> IndexPath
# IndexPath: daily cumulative index from period_start to min(as_of, period_end), + observed_to_date
def proxy_error(proxy: IndexPath, official: pl.DataFrame) -> ProxyErrorReport
```
- Pure function; no I/O. All data passed in.
- Acceptance: mean absolute proxy error < 5% of LPA where official values exist; otherwise publish the error honestly (it becomes a research result about basis between grid and station data).

### 7.3 Burn & distribution pricing (`mq.pricing.burn`, `.distribution`)
- Burn: reconstruct index for every historical season 1901–(last year) → payoff sample → mean, median, sd, P5…P95, skew, ES.
- Detrending options: none | linear | LOESS; choose via out-of-sample pricing error, document in ADR.
- Distribution candidates: Gamma, Lognormal, Weibull, KDE (Silverman + CV bandwidth), block bootstrap, and **ENSO-conditioned climatology** (fit on years with same ONI tercile).
- Selection: rolling-origin CV on log-likelihood + CRPS of the payoff; AIC as secondary only.
- Every fit logged to MLflow with params + diagnostics (QQ, PIT).

### 7.4 Stochastic simulator (C++ core, `mq.pricing.simulator`)
**Model (chain-dependent, Richardson-type):**
- Occurrence: 1st-order 2-state Markov chain, `p01(d)`, `p11(d)` via logistic GLM on Fourier harmonics of day-of-year (K = 2–3) + covariates (ONI, DMI, MJO amplitude where justified).
- Amount | wet: Gamma with seasonally varying mean (log-link GLM) and constant or seasonal shape; mixed-exponential as challenger.
- **Overdispersion fix:** draw a season-level random effect / parameter vector from the posterior (or bootstrap of fitted params) per path, so seasonal-total variance matches observed. Validation test required (below).
- Conditioning: paths start from the observed state on `as_of` (wet/dry yesterday) and add `observed_to_date`.
- Multi-station (P2): Wilks latent-Gaussian correlation across stations.

**C++ API (pybind11):**
```cpp
struct SimParams { /* daily p01,p11,shape,scale arrays; per-path param draws */ };
struct SimRequest { int n_paths; int n_days; uint64_t seed; double observed_to_date;
                    int start_state; PayoffSpec payoff; bool return_paths; };
struct SimResult  { std::vector<double> terminal_index; std::vector<double> payoff;
                    /* optional path matrix */ };
SimResult simulate(const SimParams&, const SimRequest&);
```
- Philox counter = (path_id, day) → identical results regardless of thread count.
- OpenMP over paths; no heap allocation inside the inner loop.
- Python reference implementation in NumPy (`simulator_ref.py`) for statistical cross-checks.

**Acceptance:**
- 1,000,000 paths × 92 days < 10 s on the benchmark machine (record CPU model in `docs/benchmarks/`).
- Deterministic: same seed → bit-identical output for 1, 4, 8 threads.
- Statistical: simulated vs observed (1951–2020 holdout) — wet-day frequency, mean wet-day amount, spell-length distribution, **seasonal-total sd within ±10%**, KS test on seasonal totals not rejected at 5%.
- MC error reported: standard error of fair value printed with every price.

### 7.5 Market price of risk (`mq.mpr`)
- Wang: `F*(x) = Φ(Φ⁻¹(F(x)) − λ)`; price = `E_{F*}[payoff]`. Implement by reweighting simulated/sampled payoffs (sort-based) — no re-simulation.
- Esscher: `dQ/dP ∝ exp(θ·I)`; price via self-normalised importance weights; monitor effective sample size (ESS); refuse if ESS < 1% of N.
- Calibration: for each (series, date) solve `price_Q(λ) = settle` with Brent; λ bounded in [−3, 3].
- Uncertainty: (a) parametric bootstrap over P-model parameters, (b) MC error, (c) **Bayesian pooled estimate** across dates with weak prior N(0,1) and liquidity-weighted likelihood. Report all three; headline = Bayesian posterior median + 90% credible interval + `n_obs` + total volume.
- Research outputs: λ vs days-to-expiry, λ vs volume, Wang vs Esscher consistency.
- Language rule: "early empirical estimate", never "the rainfall risk premium is X".

### 7.6 Forecasting (`mq.forecasting`)
Target at issue date `t`: distribution of **remaining-period rainfall** (and hence final index).
Model ladder (each a separate `model_id` in the ledger):

| Model | Idea | Status |
|---|---|---|
| `clim_v1` | Empirical climatology of remaining rain | Week 1, ledger live |
| `enso_clim_v1` | Climatology conditioned on ONI/DMI terciles | Week 2 |
| `analog_v1` | k-nearest past seasons on (observed-to-date anomaly, ONI, DMI, MJO) | Week 6 |
| `lgbm_q_v1` | LightGBM quantile regression (q = 0.05…0.95) + monotone rearrangement | Week 6–7 |
| `lgbm_q_cqr_v1` | + conformalized quantile regression for calibrated coverage | Week 7 |
| `tft_v1` (P2) | Temporal Fusion Transformer | Only if data + time allow; small samples (≈120 seasons) make it a weak candidate — document why if skipped |

- Training data: every (season, issue-day) pair as a row; group CV by **season** (never split a season across folds).
- Walk-forward only: train ≤ year y−1, test y.
- Metrics: CRPS, CRPSS vs `clim_v1`, pinball loss per quantile, 50%/90% coverage, PIT histogram, reliability diagram.
- Acceptance: CRPSS > 0 in walk-forward backtest **and** reported live from the ledger (whatever the sign).

### 7.7 Forecast-conditioned pricing (`mq.pricing.conditioned`)
```
observed_to_date  +  forecast quantiles for next h days  +  simulator for remainder
                         ↓ (quantile-mapping of simulated near-term totals to forecast)
                 forecast-conditioned payoff distribution (P)  →  apply λ → Q price + band
```
- Never assume monotonic shrinking uncertainty; plot band width vs time and let data speak.

### 7.8 Greeks (`mq.risk.greeks`)
- Delta: `[V(obs + Δr) − V(obs − Δr)] / 2Δr`, Δr = 10 mm (configurable); gamma likewise; theta: `V(t+1 | no-rain day) − V(t)` and `V(t+1 | climatological day) − V(t)` (show both; explain).
- **Common random numbers** (same seed) for bumped valuations — otherwise MC noise swamps the Greek. Test asserts Greek SE < 5% of value.
- Label: "model sensitivities, not exchange-standard Greeks".

### 7.9 Hedge optimiser (`mq.risk.hedge`, `.cvar`)
Inputs: exposure model `L = g(local rain)` (built-in templates: delivery-rider income loss, crop yield loss, event cancellation, construction downtime, custom piecewise-linear), joint scenarios of (local rain, contract index) from basis engine.
- Min-variance: `h* = −Cov(L, X)/Var(X)` per unit index, converted to lots with multiplier; report hedge effectiveness `1 − Var(L+hX)/Var(L)`.
- CVaR95 (Rockafellar–Uryasev LP via cvxpy/HiGHS) over scenarios; **integer lots** via enumeration over feasible lots (cap small) or MILP.
- Constraints: max order lots, position limit, margin budget, max notional, long/short allowed flags.
- Output includes residual variance, residual CVaR, basis contribution, and a "do-nothing" comparison.
- Property tests: effectiveness ∈ [0,1] for MV optimum; zero-correlation exposure → h* ≈ 0; doubling exposure doubles h*.

### 7.10 Basis engine (`mq.risk.basis`)
For each IMD grid cell within the city bounding box (and any user-dropped pin): correlation, RMSE, Kendall τ, tail dependence (upper/lower, empirical), seasonal mismatch, and **hedge effectiveness if hedged with the contract**. Output GeoJSON for a MapLibre heatmap.

### 7.11 Parametric cover designer (`mq.risk.parametric`)
Payout `= min(limit, slope · max(0, I − trigger))` (wet cover) or the dry mirror. Premium `= E_Q[payout]·(1+loading)`, discounted. Optimise (trigger, slope, limit) to minimise P(loss > threshold AND payout = 0) — the "basis-failure probability" — subject to premium ≤ budget. Grid search + Nelder–Mead refine. Case study: **synthetic** Chennai delivery-rider income exposure, labelled synthetic.

### 7.12 Scenario lab (`mq.risk.scenarios`)
Presets: El Niño / La Niña / neutral, positive/negative IOD, "2015 Chennai floods analog", "dry November", "+100 mm cloudburst tomorrow", custom shock. Each returns valuations under all methods, Greeks, and hedge P&L.

---

## 8. Pipelines & Data Quality

### 8.1 Daily DAG (`mq run daily`)
```text
06:30 IST  fetch_imd_realtime ─┐
           fetch_climate_idx  ─┼─▶ validate ─▶ DQ gate ─▶ compute_index ─▶ forecast (all models)
           fetch_ncdex_bhav   ─┘                    │            ─▶ price ─▶ mpr ─▶ greeks
                                                    │            ─▶ write ledger ─▶ export to git
                                                    └─fail─▶ alert + mark dashboard "stale"
```
- Idempotent: re-running a day produces identical outputs (except `issued_at` ledger rows, which are skipped if the same `(as_of, model_id, model_version)` exists).
- Backfill: `mq run backfill --from 1951-01-01 --to 2025-12-31 --no-ledger`.

### 8.2 DQ checks (each has an ID; results in `dq_results`)
| ID | Check | Severity |
|---|---|---|
| DQ01 | Missing dates in expected range | fail |
| DQ02 | Duplicate (date, cell) | fail |
| DQ03 | rain_mm < 0 or > 1,000 mm/day | fail |
| DQ04 | Schema drift vs pandera schema | fail |
| DQ05 | Market data older than 2 trading days | warn |
| DQ06 | Unknown contract code in bhavcopy | warn |
| DQ07 | Raw file hash changed for an already-ingested date (silent revision) | warn + log revision |
| DQ08 | Climate index revised vs previous release | info (store both) |
| DQ09 | Proxy index jumps > 3σ day-on-day | warn |
| DQ10 | Settle outside daily price band (V7) | warn |

**Gate rule:** any `fail` blocks valuation publication for that day; the dashboard shows the last good valuation with a "stale since" badge.

---

## 9. API (`/v1`)

### 9.1 Envelope (every response)
```json
{
  "data": { ... },
  "meta": {
    "as_of": "2026-11-14",
    "data_version": "a1b2c3d4e5f6",
    "model_version": "1.3.0+4f2e9a1",
    "spec_version": "2026-08-31",
    "generated_at": "2026-11-14T07:02:11+05:30",
    "synthetic": false,
    "disclaimer": "Research analytics. Not investment advice."
  }
}
```
Errors: RFC 9457 problem+json with stable `type` codes (`mq/stale-data`, `mq/unknown-series`, `mq/infeasible-hedge`).

### 9.2 Endpoints
| Method | Path | Returns |
|---|---|---|
| GET | `/v1/health`, `/v1/health/data` | liveness; data freshness per source |
| GET | `/v1/contracts` | specs + listed series + status |
| GET | `/v1/contracts/{code}/spec` | full spec YAML + sources |
| GET | `/v1/series/{id}/index?from&to` | proxy/official/error path |
| GET | `/v1/series/{id}/quotes` | settle, volume, OI |
| GET | `/v1/series/{id}/valuation?as_of&method&measure` | fair value + band + MC SE |
| GET | `/v1/series/{id}/valuations/compare` | all 4 methods side-by-side |
| GET | `/v1/series/{id}/forecast?model_id` | quantiles + fan chart data |
| GET | `/v1/series/{id}/greeks` | delta/gamma/theta + SE |
| GET | `/v1/series/{id}/mpr` | λ time series + CIs + liquidity |
| GET | `/v1/series/{id}/basis` | GeoJSON grid metrics |
| POST | `/v1/hedge` | optimal lots, effectiveness, residual risk |
| POST | `/v1/parametric/design` | optimal trigger/slope/limit + premium |
| POST | `/v1/scenarios/run` | scenario valuations |
| GET | `/v1/ledger?series&model&from&to` | ledger rows + hashes |
| GET | `/v1/ledger/verify` | chain verification result |
| GET | `/v1/track-record` | CRPS, coverage, PIT per model |
| GET | `/v1/lineage?series&as_of` | full data/model lineage |

- Pydantic schemas in `api/schemas/`; OpenAPI exported to `web/lib/api/openapi.json` in CI; TS types generated with `openapi-typescript` (CI fails if stale).
- Heavy POSTs (hedge, parametric) cap `n_paths` at 200k and time-box to 5 s; cached by request hash.
- Rate limit: 60 req/min anon; API keys (hashed) for higher limits.

---

## 10. Dashboard (Next.js)

Design language: calm, data-dense, monsoon palette (deep slate, rain-blue, saffron accents), dark/light themes, every number hoverable to reveal its lineage (`data_version`, method, as_of).

| # | Page | Key components |
|---|---|---|
| 1 | **Overview** `/` | Contract cards: latest settle, model fair-value band, premium/discount to model (bps of band), volume/OI, data-freshness pills; season progress bar; "today's rain" tile |
| 2 | **Pricing** `/series/[id]/pricing` | 4-method comparison bar w/ intervals; payoff distribution (P vs Q overlay); MC SE; method notes |
| 3 | **Forecast** `/series/[id]/forecast` | Fan chart of final index; observed-to-date line; model switcher; analog-years table |
| 4 | **Risk** `/series/[id]/risk` | Delta/gamma/theta tiles; value-vs-rain curve; λ chart with CI ribbon + volume bars |
| 5 | **Hedge Lab** `/hedge` | Exposure template picker → sliders → optimiser → lots, effectiveness, CVaR before/after, residual basis; "synthetic exposure" banner |
| 6 | **Basis Map** `/basis` | MapLibre grid heatmap (corr / effectiveness / tail dependence toggle); click cell → scatter vs index |
| 7 | **Track Record** `/track-record` | Ledger table, hash-chain status badge, link to public git repo, CRPS/coverage per model, PIT histogram |
| 8 | **Learn** `/learn` | Interactive payoff playground: drag rainfall, watch index/payoff/hedge update; glossary |
| 9 | **Methods** `/methods` | Rendered `docs/methods/*.md`, assumptions, limitations, data sources & licences, changelog |

UX rules: intervals always visible; no red/green "signal" colours for premium/discount; mobile-responsive; Lighthouse ≥ 90 performance/accessibility; skeleton loaders; empty/stale states designed explicitly.

---

## 11. Testing Strategy

| Layer | Tooling | Must cover |
|---|---|---|
| Unit | pytest | Index formula, payoff, LPA lookup, distributions, Wang/Esscher, Greeks, MV/CVaR, basis metrics, ledger hashing |
| Golden | pytest + `tests/golden/*.json` | Hand-computed index/payoff for 3 real past seasons; known λ for a synthetic case; textbook MV hedge |
| Property | Hypothesis | Rain ≥ 0; index monotone in rainfall per spec sign; Q-price = P-price at λ = 0; MV effectiveness ∈ [0,1]; hedge scales linearly with exposure; Wang price monotone in λ |
| Statistical | pytest + seeds | Simulator recovers known params from synthetic data; seasonal-total variance check; MC price within 3 SE of analytic case |
| Leakage | custom | `io` layer raises if any read exceeds `as_of`; a "time-travel" test re-runs a past date and compares to ledger |
| C++ | Catch2 | RNG reproducibility across thread counts; payoff kernels |
| Integration | docker-compose + pytest | ingest → index → price → API JSON |
| E2E | Playwright | Overview loads, Hedge Lab produces a result, Track Record verifies chain |
| Performance | `make bench` | 1M paths; API p95 < 300 ms on cached GETs |

Coverage gate: ≥ 85% on `index`, `pricing`, `mpr`, `risk`, `ledger`; ≥ 70% overall.

### 11.1 CI (`.github/workflows/ci.yml`)
lint (ruff, clang-format, eslint) → types (mypy --strict on core, tsc) → build C++ wheel → unit/property/golden → integration (services: postgres) → OpenAPI drift check → web build → Playwright (smoke) → `pip-audit` + `pnpm audit` + gitleaks. Bench job runs weekly and on `core/` changes.

---

## 12. Observability, Security, Ops
- structlog JSON with `request_id`, `series_id`, `run_id`; Sentry for API + web; `/metrics` for Prometheus (job durations, DQ failures, ledger rows/day).
- Status page section on Overview: last successful run per pipeline.
- Secrets via environment / platform secret store; gitleaks pre-commit hook.
- Public read API, CORS restricted to the web origin, rate limiting, request-size limits on POSTs.
- Backups: daily Postgres dump to object store; ledger additionally mirrored in git.

---

## 13. Milestone Plan (15 weeks, with gates)

Each milestone lists tasks to execute in order. **Gate = acceptance check that must pass before the next milestone.**

### Week 1 (5–11 Oct) — M0 Scaffold · M1 Specs · ledger live
- M0.1 Repo, uv workspace, Makefile, pre-commit, CI skeleton, docker-compose (postgres, mlflow).
- M0.2 `mq` CLI skeleton, settings, structlog, `io` layer with `as_of` enforcement + test.
- M0.3 Alembic migrations for §6.1 tables + ledger immutability trigger.
- M1.1 Source register; download & hash official NCDEX spec docs; fill `docs/VERIFY.md` (V1–V12).
- M1.2 `ContractSpec` model + YAMLs (draft where VERIFY open).
- M1.3 IMD gridded ingestion (`imdlib`) 1901–present + ONI/DMI/MJO ingestion with `release_date`.
- M1.4 `clim_v1` forecaster + ledger writer + daily export to public git repo (GitHub Actions cron).
- **Gate:** ledger has ≥ 1 verified daily row per live contract; `mq ledger verify` passes.

### Week 2 (12–18 Oct) — M2 Market data & DQ · M3 Index
- M2.1 NCDEX downloader (bhavcopy/contract pages), immutable raw storage, normalised `market_quotes`.
- M2.2 DQ01–DQ10 + gate wiring.
- M3.1 Index engine (pure) + golden tests on 3 past seasons.
- M3.2 Proxy vs official error tracking (if official values published).
- M3.3 `enso_clim_v1` into ledger.
- **Gate:** index reproducible from raw data for any past date; DQ gate blocks on injected bad data.

### Week 3 (19–25 Oct) — M4 Burn & distribution pricing
- M4.1 Historical season reconstruction; burn stats; detrending ADR.
- M4.2 Distribution zoo + rolling-origin CV; MLflow logging.
- M4.3 `valuations` writes for `burn` and `dist`.
- **Gate:** two independent P-measure prices with intervals for each series; methods note `docs/methods/burn_distribution.md`.

### Week 4 (26 Oct–1 Nov) — M5 Simulator (build)
- M5.1 GLM fitting for occurrence/amount with Fourier + covariates (Python).
- M5.2 NumPy reference simulator.
- M5.3 C++ core + pybind11 + Philox; parity tests vs reference (statistical).
- **Gate:** C++ and reference agree on mean/sd of seasonal totals within 2 SE.

### Week 5 (2–8 Nov) — M5 Simulator (validate) · M6 MPR (start)
- M5.4 Overdispersion fix + seasonal-variance validation; spell-length checks.
- M5.5 `make bench` 1M paths; thread-determinism test.
- M6.1 Wang + Esscher via reweighting; ESS guard.
- **Gate:** 1M paths < 10 s; seasonal sd within ±10%; benchmark committed.

### Week 6 (9–15 Nov) — M6 MPR (finish) · M7 Forecasting (start)
- M6.2 Daily λ calibration, bootstrap + Bayesian pooled CIs; liquidity weighting.
- M6.3 **Research note #1**: "Early estimates of the market price of rainfall risk" (2–3 pages, figures from `research/`).
- M7.1 Feature builder (as_of-safe), `analog_v1`, `lgbm_q_v1`; walk-forward harness.
- **Gate:** λ series with CIs live on API; walk-forward backtest runs end-to-end.

### Week 7 (16–22 Nov) — M7 Forecasting (finish)
- M7.2 CQR conformal calibration (`lgbm_q_cqr_v1`); reliability diagrams; CRPSS table.
- M7.3 Promote models into the daily ledger.
- **Gate:** CRPSS vs climatology reported (backtest); all models writing to ledger daily.

### Week 8 (23–29 Nov) — Buffer / exams
- Fix debt, raise coverage, write methods notes. No new features.

### Week 9 (30 Nov–6 Dec) — M8 Conditioned pricing · M9 Greeks
- M8.1 Quantile-mapping conditioning; fair-value band; band-width-vs-time plot.
- M9.1 Greeks with CRN + SE assertions.
- **Gate:** four-method comparison available daily; Greek SE < 5% of value.

### Week 10 (7–13 Dec) — M9 Hedge optimiser
- M9.2 Exposure templates; MV + CVaR (integer lots, constraints); property tests.
- M9.3 Case study: synthetic Chennai delivery-rider exposure.
- **Gate:** `/v1/hedge` returns lots + effectiveness + residual CVaR in < 5 s.

### Week 11 (14–20 Dec) — M10 Basis · M11 Parametric & Scenarios
- M10.1 Grid metrics + GeoJSON; tail dependence.
- M11.1 Parametric designer; M11.2 scenario presets.
- **Gate:** basis heatmap data + one parametric design case study.

### Week 12 (21–27 Dec) — M12 API hardening · live evaluation
- M12.1 All §9 endpoints, envelope, problem+json, caching, rate limiting, OpenAPI → TS client.
- M12.2 Live scoring of ledger forecasts so far (CRPS, coverage, PIT).
- **Gate:** contract tests for every endpoint; OpenAPI drift check green.

### Week 13 (28 Dec–3 Jan) — M13 Dashboard
- Pages 1–9 (§10), lineage hover, stale states, Playwright smoke.
- **Gate:** Lighthouse ≥ 90; E2E green; season closed → final out-of-sample scores computed.

### Week 14 (4–10 Jan) — M14 Deploy & harden
- Deploy budget path (Vercel + Fly/Render + Neon + R2); scheduled jobs; Sentry; backups; alerts (P2).
- **Gate:** public URL; 7 consecutive successful daily runs (started earlier in staging).

### Week 15 (11–17 Jan) — M15 Paper, demo, launch
- Preprint (§15), README with results table (measured numbers only), 2-minute demo video, architecture diagram, one-page summary.
- **Gate:** Definition of Done (§18) walkthrough passes on a fresh machine.

---

## 14. Risks & Fallbacks
| Risk | Signal | Fallback |
|---|---|---|
| Contracts not trading / suspended (V11) | No quotes for > 10 days | **Mode B:** price "shadow contracts" using the official spec; MPR section becomes methodology + simulation study; keep everything else |
| Official index values unavailable | V5 unresolved | Publish proxy only, with clear label; validate proxy vs station bulletins |
| IMD real-time lag/outage | DQ05/DQ01 | CHIRPS/IMERG gap-fill flagged `gapfilled=true` |
| Too few trades for λ | n_obs < 10 | Report Bayesian posterior ≈ prior honestly; pool across contracts |
| Simulator too slow | bench fails | Reduce to 250k paths + antithetic/QMC (Sobol) variance reduction; document |
| TFT not worth it | small data | Skip, document in ADR — this is a strength, not a weakness |
| Time crunch | behind by > 1 week | Drop P1/P2 in order: alerts → parametric → scenarios → basis map UI (keep basis metrics) |

---

## 15. Research Paper Outline (preprint)
**Working title:** *Pricing and Hedging India's Exchange-Traded Rainfall Futures: A Reproducible Framework with Early Evidence on the Market Price of Rainfall Risk*
1. Introduction — weather risk in India; the new contracts; contributions.
2. Contract design & index replication — proxy error.
3. Data — IMD grid, drivers, market data; leakage controls.
4. Physical-measure models — burn, distributions, chain-dependent simulator (overdispersion fix).
5. Probabilistic forecasting — ladder, walk-forward, conformal; live ledger results.
6. Pricing measure — Wang/Esscher; λ estimates with uncertainty; liquidity caveats.
7. Hedging — MV/CVaR, basis-risk geography, parametric design case study.
8. Limitations — short sample, thin market, station basis, synthetic exposures.
9. Reproducibility statement — repo, ledger, `make reproduce`.

---

## 16. Portfolio Evidence (capture at launch — measured numbers only)
1. Live dashboard URL · 2. GitHub repo · 3. Public prediction-ledger repo with hash chain · 4. Architecture diagram · 5. OpenAPI docs · 6. 1M-path benchmark · 7. λ figure with CIs · 8. Live CRPS/coverage table · 9. Hedge case study · 10. Basis heatmap · 11. Preprint · 12. 2-minute demo · 13. One-page summary.

CV line template (fill only with measured values):
> Built MonsoonQuant, an open quant platform pricing India's rainfall futures: C++ stochastic rainfall simulator ([N]M paths in [T]s), probabilistic forecasting with a public hash-chained prediction ledger ([CRPSS]% skill vs climatology, live out-of-sample), market-price-of-risk estimation and CVaR hedge optimisation.

---

## 17. Non-Negotiable Principles
1. Engines own every number; nothing is hand-typed into the UI.
2. Every number has lineage (`data/model/spec_version`, `as_of`).
3. No look-ahead — enforced in code.
4. Forecasts are timestamped publicly before outcomes.
5. Uncertainty is shown, never hidden.
6. Thin-market caveats are explicit.
7. Synthetic is labelled synthetic.
8. Claims scale with sample size.
9. Methods are public and readable.
10. Clean checkout → `make reproduce` → same figures.

---

## 18. Definition of Done
A new user can: open the site → pick RAINCHNNAI/RAINMUMBAI → see today's index, market price and four model fair values with bands → inspect the forecast fan chart and the model's live track record → read λ with its uncertainty → move a rainfall slider and watch value/Greeks change → run a synthetic exposure through Hedge Lab and see variance/CVaR reduction and basis risk on a map → open Methods for every assumption → clone the repo, run `make reproduce`, and regenerate the paper figures.

---

## Appendix A — `AGENTS.md` template (create in M0, keep ≤150 lines)
```markdown
# MonsoonQuant — Agent instructions
Spec: docs/SPEC.md (this master file). Read §0 and the current milestone before coding.

## Current milestone
M?.? — <title> — gate: <acceptance check>

## Loop
plan → failing test → implement → `make check` → PROGRESS.md entry → conventional commit

## Never
- compute or display a number outside the engines
- read data without the as_of-aware `mq.io` layer
- modify raw files, ledger rows, or golden expected values without asking
- guess any VERIFY item (see docs/VERIFY.md)
- add paid services or >50 MB deps without asking

## Commands
make bootstrap | make check | make test-golden | make bench | make dev | mq --help

## Layout
src/mq/{specs,io,pipelines,index,pricing,mpr,forecasting,risk,ledger,api} · core/ (C++) · web/ · research/

## Style
Python: typed, ruff, mypy --strict on core pkgs, pure functions for maths, Polars.
C++: C++20, clang-format, no allocation in hot loops, Philox RNG.
TS: strict, generated API types only, no `any`.
```

## Appendix B — Suggested session prompts
- *Kick-off:* "Read docs/SPEC.md fully. Create AGENTS.md from Appendix A. Then execute M0.1–M0.3 in plan mode; stop after the gate and show me `make check` output."
- *Per milestone:* "Start M5. Re-read §7.4 and §11. Propose the task breakdown and test list first; wait for my OK."
- *Verification:* "Run the time-travel leakage test for 2025-11-15 and show the diff against the ledger."
- *Review:* "Act as a skeptical quant reviewer. List the 5 weakest assumptions in the current pricing pipeline with evidence from the code."

## Appendix C — Glossary
**LPA** long-period average rainfall · **CDR** cumulative deviation of rainfall · **Burn analysis** pricing from historical payoffs · **P / Q measure** physical vs pricing probability · **MPR (λ)** market price of risk · **Wang transform** distortion of the CDF by λ · **Esscher transform** exponential tilting · **CRPS** continuous ranked probability score · **CRPSS** skill vs a reference · **PIT** probability integral transform · **CQR** conformalized quantile regression · **CVaR95** mean loss in the worst 5% · **Basis risk** mismatch between hedge index and actual exposure · **CRN** common random numbers.
