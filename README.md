# MonsoonQuant

Prices, forecasts, explains and hedges India's exchange-traded rainfall futures (RAINCHNNAI, RAINMUMBAI) — a small, auditable quant-research platform. **Research analytics, not trading advice.**

Every number on the dashboard traces back to a real engine run against real data: real NCDEX contract specs, real IMD 0.25° gridded rainfall (1951-2020 + 2023, 71 seasons, zero gaps), real ONI/DMI climate indices, and a hash-chained, append-only prediction ledger that forecasts are written to before their outcomes are known.

See `docs/SPEC.md` for the full build specification, `docs/STATUS.md` for exactly what's done vs. open, and `docs/methods/*.md` for the real findings (including the honest ones — degenerate optimizer cases, data gaps, numbers that didn't reproduce exactly) behind every milestone.

## Measured results (not claims)

| | |
|---|---|
| C++ rainfall simulator | **1,000,000 paths × 92 days in 0.80s** (budget: 10s) — Philox4x32-10, bit-identical across 1/2/4/8 OpenMP threads |
| Historical backfill | **71 real seasons** (1951-2020 + 2023, zero gaps) — extended from the original 1991-2020 window to close SPEC §7.4's statistical holdout |
| Burn analysis — RAINCHNNAI | n=31 seasons: mean 905.6mm, median 843.4mm, sd 388.5, skew 1.14 |
| Burn analysis — RAINMUMBAI | n=31 seasons: mean 2273.5mm, median 2188.8mm, sd 532.4mm (was never computed before — found a real gap, fixed it; real final 2026 season index=2167.6mm) |
| Distribution selection | 7 candidates, leave-one-out CRPS — RAINCHNNAI: `kde_cv` wins (213.01); RAINMUMBAI: `gamma` wins (313.39) |
| Forecasting ladder (walk-forward, n=31 seasons) | Every added-complexity rung underperforms plain climatology on CRPS (clim_baseline 156.4 vs. 165-202 for the 4 newer rungs) — reported honestly, not retuned to look better |
| Forecast-conditioned pricing (M8) | fair_value=810.3mm, 90% band 340.7-1482.5mm as of 2026-10-09 (h=30 days) — non-monotonic band widths confirmed on real data |
| Market price of risk — first real calibration | 6 real RAINCHNNAI market quotes ingested (2026-10-05/06, manual bhavcopy download). All 12 (series × date × transform) calibrations converged: Wang λ ≈ Esscher θ ≈ 0.02-0.06. **Zero volume/OI** — not actively trading as of this writing |
| Hedge case study (real RAINCHNNAI index, real IMD rainfall) | CVaR95 hedge hits its own position-limit cap — the real index has been positive in every one of 31 historical seasons, so an unconstrained CVaR optimum doesn't exist for this contract |
| Basis-risk grid (12 real IMD cells) | Correlation 0.96+ next to the real stations, degrading to 0.73 at the box's far corner (~60km away) |
| Public REST API | 18/18 SPEC-listed `/v1` endpoints, every one backed by a real tested engine, zero stubs |
| Dashboard | 9/9 pages, Lighthouse ≥93/100 on every page in every category (performance/accessibility/best-practices/SEO), measured against a production build |
| Prediction ledger | 12 real hash-chained rows across 5 model IDs, chain-verified (`mq ledger verify`) |

Full citations and the real (sometimes unflattering) findings behind every number: `docs/methods/*.md`. A few things that *didn't* reproduce cleanly on re-run are reported as such, not quietly fixed up — see `docs/methods/hedge.md` §6 and `docs/methods/parametric.md` §4.

## What's real vs. what's explicitly not (yet)

- **Blocked by design, not oversight**: NCDEX settlement/volume data (`bhavcopy`) automated fetch and MJO data are both bot-gated by their sources; this project documents that as policy rather than circumventing it (`docs/DECISIONS.md`). The **manual-download path is proven and in active use**: `mq run bhavcopy <csv>` ingests a file downloaded through the NCDEX website — 2 real days already ingested for RAINCHNNAI. More days (same manual path) would unlock a real Bayesian pool across dates and the λ-vs-days-to-expiry research plots.
- **Synthetic, labelled synthetic**: every hedge/parametric-cover case study uses a real location's real rainfall and the real official index, run through an illustrative (not a real business's) exposure shape — stated inline wherever it appears, never presented as more than it is.
- **Not started**: cloud deployment (M14) — this repo runs fully locally (`make dev && make check`); a 2-minute demo video and a public prediction-ledger mirror repo (both named in SPEC §16, neither buildable without a human recording a video or deciding on public hosting).
- **Your call, not changed automatically**: `mq.api.common.BASIS_YEARS` is still pinned to `[1991-2020, 2023]` (n=31) — every measured number in `docs/methods/*.md` and the preprint was produced against this window. The 71-year backfill data exists; widening the window would change all published numbers at once, so it was deliberately left as a user decision.

## Quickstart

```bash
make bootstrap   # uv sync, pnpm install, pre-commit install
make dev         # docker compose up (postgres, mlflow) via colima
make check       # lint + mypy --strict + full pytest suite
mq --help        # the mq CLI (specs, ledger, research, run)
```

Dashboard (needs `make dev` + a running API first):

```bash
PYTHONPATH=src uv run uvicorn mq.api.main:app --port 8000 &
cd web && pnpm install && pnpm run dev   # http://localhost:3000
```

Warm the API cache after starting (so the first real visitor never pays the cold-cache cost live):

```bash
mq run warm-cache --base-url http://127.0.0.1:8000
```

Run the daily ingest pipeline (IMD real-time fetch → index recompute → live ledger write, both real contracts):

```bash
mq run daily
```

Ingest a manually-downloaded NCDEX bhavcopy CSV (UDiFF format):

```bash
mq run bhavcopy path/to/bhavcopy.csv
```

Regenerate the real figures behind the preprint (`paper/preprint.md`) from the real local data (needs the IMD/ONI/DMI backfill already run — see `docs/STATUS.md`'s "How to resume work"):

```bash
make reproduce
```

## Milestone summary

| Milestone | Status | Notes |
|---|---|---|
| **M0** Scaffold | ✅ | repo, uv, Makefile, pre-commit, CI, docker-compose, `mq` CLI |
| **M1** Specs + ledger | ✅ | V1-V11 closed from official NCDEX docs; 3 verified ledger rows |
| **M2** Market data & DQ | 🟨 | Pipeline + DQ01-10 done; live fetch bot-gated; manual path proven |
| **M3** Index engine | ✅ | Real CDR index, daily-updated by `mq run daily` |
| **M4** Burn & distribution | ✅ | Both contracts fully priced; RAINMUMBAI was a real gap, now fixed |
| **M5** Simulator | ✅ | 0.80s / 1M paths; 71-season statistical holdout passed |
| **M6** MPR | 🟨 | Machinery + real calibration (2 days); more bhavcopy days needed |
| **M7** Forecasting | ✅ | 5 rungs built; all 4 newer rungs have real live ledger rows |
| **M8** Conditioned pricing | ✅ | Persisted to `valuations`; live on API + Pricing page |
| **M9** Greeks & hedge | ✅ | Delta/gamma exact; CVaR position-limit finding confirmed on real data |
| **M10** Basis risk | ✅ | 12-cell real run; seasonal mismatch wired into `basis_grid` |
| **M11** Parametric & scenarios | ✅ | Real case study; ENSO-conditioned burn valuation in scenario lab |
| **M12** API hardening | ✅ | 18/18 endpoints, rate limiting, OpenAPI/TS CI drift check |
| **M13** Dashboard | ✅ | 9 pages, Lighthouse ≥93 every page, 4 E2E specs green |
| **M14** Deploy | ⬜ | Needs your infrastructure decision |
| **M15** Paper, demo, launch | 🟨 | Preprint + `make reproduce` done; demo video + public URL need M14 |

## Layout

```
src/mq/{specs,io,pipelines,index,pricing,mpr,forecasting,risk,ledger,api,research}
core/        C++ simulator (pybind11 + OpenMP + Philox4x32-10)
web/         Next.js dashboard (9 pages)
docs/        SPEC, STATUS, PROGRESS, methods notes, architecture, VERIFY/DECISIONS
paper/       the preprint (paper/preprint.md)
research/    regenerated figures (make reproduce)
```

See `docs/SPEC.md` §5 for the full repository-layout rationale and `docs/architecture.md` for a diagram of how the pieces connect.

## Non-negotiable principles (SPEC §17)

Engines own every number — nothing is hand-typed into the UI. Every number carries its own lineage (data/model/spec version, as-of date). No look-ahead, enforced in code (`mq.io.asof`). Uncertainty is shown, never hidden. Synthetic is labelled synthetic. Claims scale with sample size (n=31 seasons is small, and every write-up says so).
