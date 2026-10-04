# Progress Log

Running log, most recent first. Each entry: date, task ID, what changed,
measured numbers.

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
