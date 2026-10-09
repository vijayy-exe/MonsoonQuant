# MonsoonQuant

Prices, forecasts, explains and hedges India's exchange-traded rainfall futures (RAINCHNNAI, RAINMUMBAI) — a small, auditable quant-research platform. **Research analytics, not trading advice.**

Every number on the dashboard traces back to a real engine run against real data: real NCDEX contract specs, real IMD 0.25° gridded rainfall (1991-2020 + 2023, 31 seasons, zero gaps), real ONI/DMI climate indices, and a hash-chained, append-only prediction ledger that forecasts are written to before their outcomes are known.

See `docs/SPEC.md` for the full build specification, `docs/STATUS.md` for exactly what's done vs. open, and `docs/methods/*.md` for the real findings (including the honest ones — degenerate optimizer cases, data gaps, numbers that didn't reproduce exactly) behind every milestone.

## Measured results (not claims)

| | |
|---|---|
| C++ rainfall simulator | **1,000,000 paths × 92 days in 0.82s** (budget: 10s) — Philox4x32-10, bit-identical across 1/2/4/8 OpenMP threads |
| Historical burn analysis | 31 real seasons: mean 905.6mm, median 843.4mm, skew 1.14 |
| Distribution selection | 7 candidates, leave-one-out CRPS — `kde_cv` wins (213.01), narrowly ahead of gamma (213.14) |
| Forecasting ladder (walk-forward, n=31 seasons) | Every added-complexity rung underperforms plain climatology on CRPS (clim_baseline 156.4 vs. 165-202 for the 4 newer rungs) — reported honestly, not retuned to look better |
| Hedge case study (real RAINCHNNAI index, real IMD rainfall) | CVaR95 hedge hits its own position-limit cap — the real index has been positive in every one of 31 historical seasons, so an unconstrained CVaR optimum doesn't exist for this contract |
| Basis-risk grid (12 real IMD cells) | Correlation 0.96+ next to the real stations, degrading to 0.73 at the box's far corner (~60km away) |
| Public REST API | 18/18 SPEC-listed `/v1` endpoints, every one backed by a real tested engine, zero stubs |
| Dashboard | 9/9 pages, Lighthouse ≥93/100 on every page in every category (performance/accessibility/best-practices/SEO), measured against a production build |
| Prediction ledger | 8 real hash-chained rows, chain-verified (`mq ledger verify`) |

Full citations and the real (sometimes unflattering) findings behind every number: `docs/methods/*.md`. A few things that *didn't* reproduce cleanly on re-run are reported as such, not quietly fixed up — see `docs/methods/hedge.md` §6 and `docs/methods/parametric.md` §4.

## What's real vs. what's explicitly not (yet)

- **Blocked by design, not oversight**: NCDEX settlement/volume data (`bhavcopy`) and MJO data are both bot-gated by their sources; this project documents that as policy rather than circumventing it (`docs/DECISIONS.md`). This is why the market-price-of-risk (λ) estimates and the P-vs-Q pricing comparison stay illustrative — there's no real settlement price to calibrate λ against yet.
- **Synthetic, labelled synthetic**: every hedge/parametric-cover case study uses a real location's real rainfall and the real official index, run through an illustrative (not a real business's) exposure shape — stated inline wherever it appears, never presented as more than it is.
- **Not started**: cloud deployment (M14) — this repo runs fully locally (`make dev && make check`); a 2-minute demo video and a public prediction-ledger mirror repo (both named in SPEC §16, neither buildable without a human recording a video or deciding on public hosting).

## Quickstart

```bash
make bootstrap   # uv sync, pnpm install, pre-commit install
make dev         # docker compose up (postgres, mlflow) via colima
make check       # lint + mypy --strict + full pytest suite
mq --help        # the mq CLI (specs, ledger, research)
```

Dashboard (needs `make dev` + a running API first):

```bash
PYTHONPATH=src uv run uvicorn mq.api.main:app --port 8000 &
cd web && pnpm install && pnpm run dev   # http://localhost:3000
```

Regenerate the real figures behind the preprint (`paper/preprint.md`) from the real local data (needs the IMD/ONI/DMI backfill already run — see `docs/STATUS.md`'s "How to resume work"):

```bash
make reproduce
```

## Layout

```
src/mq/{specs,io,pipelines,index,pricing,mpr,forecasting,risk,ledger,api,research}
core/        C++ simulator (pybind11 + OpenMP + Philox4x32-10)
web/         Next.js dashboard
docs/        SPEC, STATUS, methods notes, architecture, VERIFY/DECISIONS
paper/       the preprint
research/    regenerated figures (`make reproduce`)
```

See `docs/SPEC.md` §5 for the full repository-layout rationale and `docs/architecture.md` for a diagram of how the pieces connect.

## Non-negotiable principles (SPEC §17)

Engines own every number — nothing is hand-typed into the UI. Every number carries its own lineage (data/model/spec version, as-of date). No look-ahead, enforced in code (`mq.io.asof`). Uncertainty is shown, never hidden. Synthetic is labelled synthetic. Claims scale with sample size (n=31 seasons is small, and every write-up says so).
