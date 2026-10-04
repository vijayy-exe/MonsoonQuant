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
| 1 | **M1** Specs + ledger live | ⬜ not started | ledger ≥ 1 verified daily row/contract; `mq ledger verify` passes | **Blocked on you:** need official NCDEX contract-spec PDFs for RAINCHNNAI/RAINMUMBAI to close VERIFY V1–V12 (docs/VERIFY.md) |
| 2 | **M2** Market data & DQ | ⬜ not started | DQ gate blocks on bad data | |
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

## M0 detail (done this session)

| Item | Status |
|---|---|
| Repo layout (SPEC §5) | ✅ |
| git init (local only, no remote) | ✅ |
| uv workspace, Python 3.12, `pyproject.toml` | ✅ (`uv sync` → 44 pkgs) |
| Makefile (`bootstrap/check/test-golden/bench/ingest/reproduce/dev/down`) | ✅ (`ingest`/`reproduce` are forward stubs — no `mq run daily` / `mq research reproduce` yet) |
| pre-commit (ruff, mypy, clang-format, gitleaks) | ✅ installed; not yet run `--all-files` |
| CI skeleton (`.github/workflows/ci.yml`) | ✅ written; not yet run on a real push/PR; web + C++ jobs commented as TODO |
| docker-compose (postgres:16 on **5433**, mlflow) | ✅ both up locally via colima |
| `mq` CLI (Typer) — `--help`, `version` | ✅ |
| Settings (pydantic-settings) + structlog | ✅ |
| `mq.io.asof` as_of-aware layer + look-ahead test | ✅ 5 unit tests |
| Alembic migrations — all 11 §6.1 tables | ✅ applied to live Postgres |
| `prediction_ledger` immutability trigger | ✅ 2 integration tests prove UPDATE/DELETE blocked |
| `CLAUDE.md` (Appendix A template) | ✅ |
| `docs/{PROGRESS,DECISIONS,VERIFY,STATUS}.md` | ✅ this session |
| `make check` (lint+format+mypy strict+pytest) | ✅ green: 0 lint issues, 23 files type-clean, 7/7 tests pass |

**Not part of M0, correctly deferred:** source register / `mq sources add`,
`ContractSpec` model + YAMLs, IMD/ONI/DMI/MJO ingestion, `clim_v1`
forecaster, ledger writer + hash chain, public-repo export job — these are
M1.

---

## Feature catalogue (SPEC §1.4)

| ID | Feature | Pri | Milestone | Status |
|---|---|---|---|---|
| F01 | Versioned contract-spec registry (YAML + source PDFs + hashes) | P0 | M1 | ⬜ |
| F02 | Market-data ingestion (settlement, volume, OI) with provenance | P0 | M2 | ⬜ |
| F03 | Gridded rainfall ingestion (IMD 0.25°) + station mapping | P0 | M2 | ⬜ |
| F04 | Climate drivers (ONI, DMI/IOD, MJO phase) | P0 | M2 | ⬜ |
| F05 | Data-quality gate blocking publication | P0 | M2 | ⬜ |
| F06 | Index replication engine + proxy-error tracking | P0 | M3 | ⬜ |
| F07 | **Prediction Ledger** (append-only, hash-chained, public) | P0 | M1→ | 🟨 DB table + immutability trigger done; hash-chain writer/verify/export still M1 |
| F08 | Historical burn analysis (with detrending options) | P0 | M4 | ⬜ |
| F09 | Index-distribution pricing (Gamma/Lognormal/KDE/bootstrap/ENSO-conditioned) | P0 | M4 | ⬜ |
| F10 | C++ chain-dependent stochastic rainfall simulator (1M paths < 10s) | P0 | M5 | ⬜ |
| F11 | Market price of risk (Wang + Esscher) w/ bootstrap/Bayesian CIs | P0 | M6 | ⬜ |
| F12 | Probabilistic forecaster (climatology → analog → LightGBM-quantile + conformal) | P0 | M7 | ⬜ |
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

All 12 items (V1–V12) are 🔴 **open** — none can be closed without the
official NCDEX contract-specification PDFs. This blocks real M1 work on
`ContractSpec` YAMLs (DRAFT-only is possible meanwhile).

---

## Open blockers / needs-from-you

1. **Official contract specs** — download NCDEX spec PDFs for RAINCHNNAI
   and RAINMUMBAI so VERIFY V1–V12 can be closed (M1.1–M1.2).
2. **C++ toolchain** — CMake is present; `pybind11`/`scikit-build-core`/
   OpenMP not yet installed or exercised. Needed starting M5 (week 4),
   not before.
3. **CDS API key** (Copernicus, for ERA5/SEAS5) — only needed from M1.3
   onward if ERA5 features are pursued; `MQ_CDS_API_KEY` placeholder is in
   `.env.example`.
4. **GitHub remote** — not created yet (local git only, per your request).
   Needed before M1.4's "daily export to a public ledger repo" can be wired
   up for real.

## Known environment quirks (don't re-debug these — see docs/DECISIONS.md)

- Local Postgres is on **port 5433**, not 5432 (a native Homebrew Postgres
  already owns 5432 on this machine).
- Docker runs via **colima** (`colima start` if `docker compose` can't
  reach the daemon).
- Always let the Makefile's `PYTHONPATH` export do its job — don't remove
  it; it works around a macOS-only `uv`/CPython 3.12 interaction that
  breaks `import mq`.

---

## How to resume work

```bash
cd ~/Documents/MonsoonQuant
colima start                 # if docker isn't already running
make dev                     # postgres + mlflow
make check                   # should be green
```
Then start M1 per `docs/PROMPTS.md` ("M1.1–M1.2 — Contract specs & VERIFY").
