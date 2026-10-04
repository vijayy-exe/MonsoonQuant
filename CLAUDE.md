# MonsoonQuant — Claude Code instructions

Spec: docs/SPEC.md (this master file — copied from the original build spec).
Read §0 and the current milestone before coding. Status/tracker: docs/STATUS.md.

## Current milestone
M1 — Specs, climate ingestion, ledger live — gate met for RAINCHNNAI (1 real
ledger row, `mq ledger verify` passes). RAINMUMBAI deferred (no open proxy
season today) and real VERIFY closure still needs the official NCDEX PDFs.
Next: M2 (market data ingestion, DQ05-DQ10) on current DRAFT specs, or
address an open blocker in docs/STATUS.md first.

M0 (scaffold) and M1 (specs/loader, IMD+ONI+DMI ingestion, ledger hash
chain + writer + verify + export) are done — see docs/STATUS.md for the
full breakdown and docs/PROGRESS.md for measured numbers.

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

## Local dev gotchas
- Postgres runs in docker-compose on **host port 5433**, not 5432 — a native
  Homebrew `postgresql@15` service already owns 5432 on this machine. Don't
  touch that service; don't move this project back to 5432 without checking.
- Docker runtime is **colima** (`colima start`), not Docker Desktop (not
  installed). `docker compose` needs colima running first.
- macOS + uv quirk: `uv run` sets the editable-install `.pth` file's
  UF_HIDDEN flag, which CPython 3.12's site.py silently skips, breaking
  `import mq`. The Makefile exports `PYTHONPATH=$(CURDIR)/src` to sidestep it
  entirely — don't remove that export. CI (Linux) is unaffected. See
  docs/DECISIONS.md.

## Style
Python: typed, ruff, mypy --strict on core pkgs, pure functions for maths, Polars.
C++: C++20, clang-format, no allocation in hot loops, Philox RNG.
TS: strict, generated API types only, no `any`.
