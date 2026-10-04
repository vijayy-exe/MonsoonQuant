# MonsoonQuant — Status: what's done, what's left

Source of truth: `docs/SPEC.md`. This file is the single tracking sheet —
update it at the end of every milestone (alongside a `docs/PROGRESS.md`
entry). Status legend: ✅ done · 🟨 in progress · ⬜ not started.

Repo: `~/Documents/MonsoonQuant` (local git, not yet pushed anywhere).

---

## Milestones (SPEC §13 — 15-week plan, Mon 5 Oct 2026 → Sun 17 Jan 2027)

| Week | Milestone | Status | Gate | Notes |
|---|---|---|---|---|
| 1 | **M0** Scaffold | ✅ done | `make check` green | repo, uv, Makefile, pre-commit, CI skeleton, docker-compose, `mq` CLI, settings, structlog, as_of io layer + test, Alembic + ledger trigger |
| 1 | **M1** Specs + ledger live | ✅ done | ledger ≥ 1 verified daily row/contract; `mq ledger verify` passes | RAINCHNNAI and RAINMUMBAI specs **fully resolved from official NCDEX documents** (V1-V11 closed). RAINCHNNAI has a real verified ledger row; RAINMUMBAI's season is closed for 2026 (see below) |
| 2 | **M2** Market data & DQ | 🟨 pipeline built, no real data yet | DQ gate blocks on bad data | NCDEX bhavcopy parser/normaliser + DQ05-DQ10 built and tested against the real documented schema; live fetch blocked (bot-gated), needs a manually-downloaded CSV |
| 2 | **M3** Index engine | 🟨 engine done, DB write + proxy_error pending | index reproducible for any past date | `compute_index` implements the real CDR methodology exactly, golden-tested (hand-computed values, caught a real int8-overflow bug). Not yet wired to write `index_values` rows or compare vs an official series |
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

## M0 detail (done)

Repo layout, git, uv workspace, Makefile, pre-commit, CI skeleton,
docker-compose (postgres:16 on port **5433**, mlflow), `mq` CLI, settings,
structlog, `mq.io.asof` as_of-aware layer, Alembic migrations (all 11
§6.1 tables), `prediction_ledger` immutability trigger (UPDATE/DELETE
proven blocked at the DB level). See `docs/PROGRESS.md` 2026-10-04 entry
for the full list.

---

## M1 detail (done — specs fully resolved)

| Item | Status |
|---|---|
| Source register (`mq.specs.sources`, `mq sources add`/`list`) | ✅ |
| `ContractSpec` model + loader (`TODO_VERIFY` sentinel, `--allow-draft`) | ✅ |
| **Real NCDEX contract specs found and registered** | ✅ 9 official PDFs hashed in `specs/sources/raw/` (contract specs, product notes, launch circulars, UDiFF format spec) |
| `specs/contracts/RAINCHNNAI/2026-08-31.yaml` | ✅ **fully resolved**, loads without `--allow-draft` |
| `specs/contracts/RAINMUMBAI/2026-05-29.yaml` | ✅ **fully resolved**, loads without `--allow-draft` |
| `mq specs validate` CLI | ✅ |
| DQ01–DQ04 gate (`mq.pipelines.dq`) | ✅ |
| IMD 0.25° gridded rainfall ingestion (`mq.pipelines.imd`) | ✅ historical + near-real-time, both DQ-gated |
| **IMD historical backfill 1991-2020** | 🟨 running (background, resumable) — see "Live state" below |
| ONI / DMI ingestion (`mq.pipelines.climate_idx`) | ✅ live: ONI 920 rows, DMI 1877 rows |
| MJO ingestion | 🟨 parser done, tested; live fetch blocked (BoM bot-gate, docs/DECISIONS.md) |
| `clim_v1` climatology forecaster | ✅ |
| Ledger hash chain + writer + verify + export | ✅ tamper detection proven |
| **Real ledger rows**: RAINCHNNAI, `clim_v1` v0.1.0 (proxy Oct-Dec window) and v0.2.0 (real Sep-Dec window, post-VERIFY) | ✅ both verified, chain intact |
| Daily export → public GitHub repo + Actions cron | ⬜ deferred — no GitHub remote (local git only, per your instruction) |
| RAINMUMBAI ledger row | ⬜ its real period (Jun 1-Sep 30) is closed for 2026 as of today (Oct 4) — nothing to forecast until Jun 2027 |

### VERIFY resolution (see docs/VERIFY.md for full citations)
Found the official NCDEX documents myself (public downloads linked from
`ncdex.com/products/RAINCHNNAI` and `/RAINMUMBAI`, robots.txt allows
everything) rather than waiting — closed **V1-V11**. Real values differ
from the earlier placeholder/proxy assumptions in one important way:
RAINCHNNAI's real period is **Sep 1-Dec 31** (not the Oct 1 start used in
the first ledger row — that row is kept, a corrected one was added, since
the ledger is append-only). V12 (data-redistribution licensing) stays
open — no document states explicit terms.

### Honesty note on the ledger rows
RAINCHNNAI has **3 ledger rows** now, each a progressively better
`clim_v1`: v0.1.0 (n=1, proxy Oct-Dec window), v0.2.0 (n=1, real Sep-Dec
window post-VERIFY), v0.3.0 (**n=25, real multi-year climatology**, after
the backfill below completed — quantiles P5=357mm, P50=697mm, P95=1769mm,
a genuine spread rather than a degenerate point). `mq ledger verify`: 3
rows, chain intact. Station coordinates are still public engineering
placeholders, not yet the official IMD metadata (noted in the YAML
comments) — that's the main remaining honesty caveat.

---

## M2 detail (pipeline built this session)

| Item | Status |
|---|---|
| NCDEX UDiFF bhavcopy format — found and registered the real spec | ✅ `ncdex_udiff_bhavcopy_format_2024` (34-column schema with ISO tags) |
| `mq.pipelines.ncdex`: parse → filter → normalise → DQ gate → upsert | ✅ tested against a schema-accurate synthetic fixture (6 unit + 2 integration tests) |
| DQ05 (stale data), DQ06 (unknown contract code), DQ07 (silent raw-file revision), DQ10 (settle outside DPL band) | ✅ |
| DQ08 (climate index revision), DQ09 (proxy index jump >3σ) | ⬜ deferred — need M3's index engine to exist first |
| **Live bhavcopy fetch** | 🔴 blocked — ncdex.com's `/api/bhavcopy` sits behind a JS fingerprint/bot-detection challenge (confirmed via the page's own served JS). Not worked around, same policy as BoM. Needs either a manually-downloaded CSV or a real browser session (claude-in-chrome wasn't connected this session) |

---

## M3 detail (index engine built this session)

| Item | Status |
|---|---|
| `mq.index.lpa.compute_daily_lpa` — climatological per-day LPA from `rain_grid` | ✅ |
| `mq.index.engine.compute_index` — real CDR methodology (season-LPA anchor + cumulative daily deviation) | ✅ pure function, raises loudly on drafts or data gaps |
| Golden test, hand-computed before encoding expected values | ✅ 4 tests, including a deliberate missing-data case |
| `index_values` DB writes, `mq.index.proxy.proxy_error` | ⬜ not started — needs an official index series to compare against, which isn't available (same bot-gate/licensing situation as market data) |

---

## Live state (data on disk right now)

- **IMD historical backfill 1991-2020: done.** 23/30 years ingested this
  session (plus the pre-existing 2023) = **25 years of real IMD rainfall**
  in `data/parquet/rain_grid/source=imd/`. Missing: 1999, 2000, 2001,
  2009, 2013, 2019 (transient IMD server timeouts/connection errors, not
  permanent gaps — rerun individually later if a full 30 matters:
  `write_rain_grid_year(1999)` etc. via `PYTHONPATH=src uv run mq` or a
  Python shell). The backfill script
  (`.scratch/backfill.py`, scratch-only, not committed) uses a 120s
  per-year subprocess timeout so one stuck request can't hang the whole
  run — reusable if a future backfill is needed.
- **IMD real-time data**: Oct 1-3 2026 (full), Sep 1-10 2026 (partial —
  Sep 11-30 still missing). The IMD real-time server was under sustained
  strain by the end of this session (repeated timeouts on both the
  historical and real-time endpoints) — deliberately stopped retrying
  rather than keep hammering a public government server. Filling Sep
  11-30 is what's needed before `compute_index` can produce a complete
  live CDR value for RAINCHNNAI today (it currently raises a clear
  "missing rainfall data" error for that gap, by design).

---

## Feature catalogue (SPEC §1.4)

| ID | Feature | Pri | Milestone | Status |
|---|---|---|---|---|
| F01 | Versioned contract-spec registry (YAML + source PDFs + hashes) | P0 | M1 | ✅ done, specs fully resolved |
| F02 | Market-data ingestion (settlement, volume, OI) with provenance | P0 | M2 | 🟨 pipeline done; live fetch blocked (bot-gate) |
| F03 | Gridded rainfall ingestion (IMD 0.25°) + station mapping | P0 | M2 | 🟨 **25 years real data** (1991-2020 minus 6 gap years, + 2023) ingested; station identity resolved (V2), exact coordinates still a placeholder |
| F04 | Climate drivers (ONI, DMI/IOD, MJO phase) | P0 | M2 | 🟨 ONI+DMI live; MJO fetch-blocked (BoM) |
| F05 | Data-quality gate blocking publication | P0 | M2 | 🟨 DQ01-07, DQ10 done; DQ08-09 need M3 |
| F06 | Index replication engine + proxy-error tracking | P0 | M3 | 🟨 `compute_index` done, golden-tested; proxy_error + DB writes pending |
| F07 | **Prediction Ledger** (append-only, hash-chained, public) | P0 | M1→ | 🟨 fully working locally; public GitHub mirror deferred (no remote) |
| F08 | Historical burn analysis (with detrending options) | P0 | M4 | ⬜ |
| F09 | Index-distribution pricing (Gamma/Lognormal/KDE/bootstrap/ENSO-conditioned) | P0 | M4 | ⬜ |
| F10 | C++ chain-dependent stochastic rainfall simulator (1M paths < 10s) | P0 | M5 | ⬜ |
| F11 | Market price of risk (Wang + Esscher) w/ bootstrap/Bayesian CIs | P0 | M6 | ⬜ |
| F12 | Probabilistic forecaster (climatology → analog → LightGBM-quantile + conformal) | P0 | M7 | 🟨 clim_v1 (rung 1) done |
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

## VERIFY checklist (SPEC §3.2) — see docs/VERIFY.md for full citations

**V1-V11 closed** from official NCDEX documents (contract specs, product
notes, launch circulars — all hashed in `specs/sources/`). **V12** (data
redistribution licensing) stays 🔴 open — no sourced document states
explicit terms; treat as not cleared for redistribution.

---

## Open blockers / needs-from-you

1. **MJO (BoM) blocked** — bom.gov.au blocks this network's automated
   access outright. Options: a different network, BoM's
   `webreg@bom.gov.au` registered-user service, or deprioritize (lowest
   priority of the three climate drivers for NE monsoon per SPEC §3.1).
2. **NCDEX bhavcopy live fetch blocked** — bot-detection/fingerprint
   challenge on their API. Options: manually download a bhavcopy CSV and
   hand it to `write_market_quotes()`, or revisit with real browser
   automation (claude-in-chrome) when available.
3. **V12 data licensing** — genuinely unresolved in any public NCDEX
   document; may just stay open permanently (consistent with SPEC's
   research-only positioning).
4. **C++ toolchain** — CMake present; pybind11/scikit-build-core/OpenMP
   not yet installed. Needed starting M5 (week 4), not before.
5. **CDS API key** (Copernicus/ERA5) — only needed if ERA5 features are
   pursued; placeholder in `.env.example`.
6. **GitHub remote** — not created yet (local git only, per your
   instruction). Needed for the ledger's public-repo mirror credibility
   feature (SPEC §2.1).
7. **Full IMD backfill vs 1991-2020** — chose the IMD/NCDEX's own 30-year
   LPA base period as a well-justified default (also exactly matches
   RAINMUMBAI's cited LPA window; RAINCHNNAI's is 1971-2020 if an even
   longer history is wanted later).

## Known environment quirks (don't re-debug these — see docs/DECISIONS.md)

- Local Postgres is on **port 5433**, not 5432 (native Homebrew Postgres
  owns 5432).
- Docker runs via **colima** (`colima start` if needed).
- Keep the Makefile's `PYTHONPATH` export — works around a macOS/uv/
  CPython 3.12 interaction that breaks `import mq`.
- `imdlib` real-time product writes one raw file per day; historical
  archive writes one per year — `mq.pipelines.imd` has separate
  fetch/write functions for each (`*_realtime` suffix).
- IMD's historical server is occasionally slow/unresponsive for an
  individual year (not a pattern tied to which year) — any backfill loop
  should use a per-year timeout, not assume every year responds quickly.

---

## How to resume work

```bash
cd ~/Documents/MonsoonQuant
colima start                 # if docker isn't already running
make dev                     # postgres + mlflow
make check                   # should be green
tail -f .scratch/backfill.log  # check IMD backfill progress, if still running
```
Next: M3 (index engine) is now unblocked with the real CDR methodology
known. Or address an open blocker above.
