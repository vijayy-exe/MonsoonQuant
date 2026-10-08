# MonsoonQuant — Claude Code instructions

Spec: docs/SPEC.md (this master file — copied from the original build spec).
Read §0 and the current milestone before coding. Status/tracker: docs/STATUS.md.

## Current milestone
M0-M8 are done. VERIFY V1-V11 closed from real official NCDEX documents;
both contract specs fully resolved. Real CDR index, burn analysis,
distribution selection, and a C++ chain-dependent simulator (pybind11 +
OpenMP + Philox4x32-10, 1M paths in 0.8s, deterministic across thread
counts, verified against the NumPy reference) are all built, tested, and
run against real IMD data. M6's Wang/Esscher MPR machinery is built,
tested, and demoed against real M4 data (illustrative settle only — no
real settlement data exists yet). M7's 5 forecasting rungs
(clim_v1/enso_clim_v1/analog_v1/lgbm_q_v1/lgbm_q_cqr_v1) are all built
and real-backtested — every newer rung honestly underperforms
climatology at n=31 seasons (reported, not hidden or retuned), but
conformal calibration demonstrably fixes coverage anyway; tft_v1 (P2)
is deliberately skipped with reasoning on record. M8's forecast-
conditioned pricing (quantile-mapped simulator splice) is built and
confirms SPEC's own "never assume monotonic shrinking uncertainty" on
a real end-to-end run. M9's Greeks are built (delta/gamma exact by the
CDR index's own additive structure; theta meets SPEC's SE<5% bar with
enough paths via the C++ core). M10's basis engine is built and
real-run (sanity-confirmed: cells nearest the real stations score
highest correlation/hedge-effectiveness). M9's hedge optimiser
(min-variance + CVaR95 via scipy's HiGHS, no cvxpy needed) is built and
real-run too — found that position limits are load-bearing for the
CVaR optimizer specifically, since the real RAINCHNNAI index has been
positive in every one of its 31 historical seasons. M11's parametric
cover designer is built and real-run (SPEC's own stated synthetic
Chennai delivery-rider case study: basis-failure probability 25.8% →
3.2%; also caught a real finding that an unconstrained trigger grid
lets the optimizer find a degenerate near-always-pay cover — not a
bug, a legitimate optimum of SPEC's literal objective). M11's scenario
lab is built and real-run too (8 scenarios incl. a real 2015 historical
analog; delta=1.0/gamma≈0 confirmed across every shock). M2's NCDEX
bhavcopy live fetch stays bot-gated (same as MJO/BoM) — not worked
around, documented as policy; it also blocks M6/M8's real calibration.
M0-M11 are all done. M12 (API) is in progress: 15 of 18 endpoints built
(health/contracts/series-valuation/index/quotes/mpr/forecast/basis/
ledger/hedge/parametric-design), confirmed via a real uvicorn run and
real integration tests against the real DB, which also surfaced and
fixed several genuine gaps — a valuations/compare join that would've
silently dropped a method, basis's ~48s uncached latency (fixed with a
request-hash cache), RAINCHNNAI's listed series repeatedly going
missing from the contracts table (root-caused: a test's own real
teardown deleting the shared real registration; fixed permanently with
an idempotent `mq specs seed-registry` command wired into `make
check`), and a real degenerate-CVaR hedge case (unconstrained
`/v1/hedge` genuinely hits the 10,000-lot fallback, reproducing
`docs/methods/hedge.md`'s own finding live, not sanitized). Remaining:
greeks (needs a real model-fitting pipeline first), scenarios/run (may
need the same pipeline work as greeks), track-record/lineage.

See docs/STATUS.md for the full breakdown, docs/PROGRESS.md for measured
numbers, and docs/VERIFY.md / docs/DECISIONS.md for what's resolved vs.
still open (V12 licensing, MJO/BoM block, bhavcopy fetch block).

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
- MLflow runs on **host port 5001**, not 5000 — macOS's AirPlay Receiver
  (ControlCenter) owns 5000 by default and silently 403s anything sent
  there before Docker even sees it.
- macOS + uv quirk: `uv run` sets the editable-install `.pth` file's
  UF_HIDDEN flag, which CPython 3.12's site.py silently skips, breaking
  `import mq`. The Makefile exports `PYTHONPATH=$(CURDIR)/src` to sidestep it
  entirely — don't remove that export. CI (Linux) is unaffected. See
  docs/DECISIONS.md.

## Style
Python: typed, ruff, mypy --strict on core pkgs, pure functions for maths, Polars.
C++: C++20, clang-format, no allocation in hot loops, Philox RNG.
TS: strict, generated API types only, no `any`.
