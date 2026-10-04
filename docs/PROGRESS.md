# Progress Log

Running log, most recent first. Each entry: date, task ID, what changed,
measured numbers.

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
