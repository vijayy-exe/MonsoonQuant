# Progress Log

Running log, most recent first. Each entry: date, task ID, what changed,
measured numbers.

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
