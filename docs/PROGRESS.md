# Progress Log

Running log, most recent first. Each entry: date, task ID, what changed,
measured numbers.

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
