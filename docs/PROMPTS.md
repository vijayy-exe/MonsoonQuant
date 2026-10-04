# MonsoonQuant — Claude Code Prompt Sheet

Put this file in `docs/PROMPTS.md` next to `docs/SPEC.md`.
Copy and paste one prompt at a time. Wait for each gate to pass before moving on.
Use **plan mode** (Shift+Tab) for every milestone start. Run `/clear` between milestones.

---

## 0. Session start (use at the beginning of EVERY session)
```
Read CLAUDE.md and docs/PROGRESS.md. Tell me in 5 lines: current milestone, last completed task,
open VERIFY items, failing tests (run `make check`), and the next task you propose. Do not code yet.
```

---

## Week 1 — M0 Scaffold · M1 Specs · Ledger live

### M0 — Scaffold
```
Read docs/SPEC.md fully. Create CLAUDE.md from Appendix A (current milestone = M0).
Then plan M0.1–M0.3 from §13 Week 1: repo layout (§5), uv workspace, Makefile targets (§0.5),
pre-commit (ruff, mypy, clang-format, gitleaks), CI skeleton (§11.1), docker-compose (postgres, mlflow),
Typer CLI `mq`, structlog, settings, and the as_of-aware `mq.io` layer with a test that fails on look-ahead reads.
Add Alembic migrations for all §6.1 tables plus prediction_ledger (§2.1) with an immutability trigger.
Show the plan first. After I approve, implement and stop at the gate with `make check` output.
```

### M1.1–M1.2 — Contract specs & VERIFY
```
Start M1.1–M1.2. Create docs/VERIFY.md with V1–V12 from §3.2 as an open checklist.
Build the source register (specs/sources/*.yaml) and a `mq sources add <pdf>` command that hashes (SHA-256)
and stores files immutably. Implement the ContractSpec pydantic model (§7.1) and a loader that rejects
unresolved VERIFY fields unless --allow-draft. Create DRAFT YAMLs for RAINCHNNAI and RAINMUMBAI.
Do NOT invent any contract value — leave TODO_VERIFY and list exactly which documents I must download.
```
*(You download the NCDEX spec PDFs, then:)*
```
I added the official documents to specs/sources/raw/. Register them, read them, and close every VERIFY item
you can, quoting the clause and page in docs/VERIFY.md. List anything still unresolved.
```

### M1.3 — Climate data ingestion
```
Start M1.3. Implement IMD 0.25° gridded rainfall ingestion with imdlib (1901–present) into Parquet per §6.2,
plus ONI, DMI and MJO ingestion with a mandatory release_date column. Add pandera schemas and DQ01–DQ04.
Keep raw files immutable and content-addressed. Show row counts and date ranges when done.
```

### M1.4 — Prediction ledger + climatology forecaster
```
Start M1.4. Implement clim_v1 (empirical climatology of remaining-period rainfall → final index quantiles),
the ledger writer with hash chain (§2.1), `mq ledger verify`, and a daily export job to a separate public repo
(ledger/YYYY/MM/DD.jsonl) via GitHub Actions cron. Write tests that prove UPDATE/DELETE fail and a tampered
row breaks verification. Run it for today and show the ledger row + verify output.
```

---

## Week 2 — M2 Market data & DQ · M3 Index

### M2
```
Start M2. Build the NCDEX downloader for bhavcopy/contract data (check robots/ToS first and tell me),
store raw files immutably, normalise to market_quotes. Implement DQ05–DQ10 and the publication gate (§8.2).
Add a test that injects bad data and proves publication is blocked. Show the last 10 quotes per series.
```

### M3
```
Start M3. Implement compute_index as a pure function (§7.2). Write golden tests by hand-computing the index
for 3 past seasons — show me the hand calculation before encoding expected values. Add proxy_error tracking
if official values exist. Add enso_clim_v1 to the ledger. Gate: index reproducible for any past date.
```

---

## Week 3 — M4 Burn & distribution pricing
```
Start M4. Implement burn analysis (§7.3) across all historical seasons with detrending options and record the
detrending choice as an ADR in docs/DECISIONS.md with out-of-sample evidence. Then fit Gamma, Lognormal, Weibull,
KDE, bootstrap and ENSO-conditioned climatology with rolling-origin CV (log-likelihood + CRPS), log to MLflow,
and write valuations for burn and dist. Write docs/methods/burn_distribution.md. Show a results table.
```

---

## Week 4 — M5 Simulator (build)
```
Start M5.1–M5.3. Re-read §7.4 and §11. First fit occurrence (logistic GLM) and amount (Gamma GLM) models with
Fourier terms + covariates in Python. Then write a NumPy reference simulator. Then the C++20 core with pybind11,
scikit-build-core, OpenMP and Philox RNG keyed by (path_id, day). Propose the test list first.
Gate: C++ and reference agree on mean/sd of seasonal totals within 2 standard errors.
```

## Week 5 — M5 validate · M6 start
```
Start M5.4–M5.5. Validate the simulator against 1951–2020 holdout: wet-day frequency, wet-day amount,
spell lengths, and seasonal-total sd. If seasonal sd is under-dispersed, implement the per-path parameter-draw
fix and show before/after. Run `make bench` for 1M paths and confirm bit-identical output for 1/4/8 threads.
Save results in docs/benchmarks/.
```
```
Start M6.1. Implement Wang and Esscher transforms by reweighting simulated payoffs (no re-simulation),
with an ESS guard for Esscher. Property tests: λ=0 gives P-price; Wang price monotone in λ.
```

---

## Week 6 — M6 finish · M7 start
```
Start M6.2–M6.3. Calibrate λ daily per series with Brent, then add bootstrap CIs and a liquidity-weighted
Bayesian pooled estimate (prior N(0,1)). Exclude zero-volume days from the headline and report them separately.
Write research/mpr_note.py that produces all figures, and draft docs/methods/mpr.md as a 2–3 page research note.
Use cautious language: "early empirical estimate".
```
```
Start M7.1. Build an as_of-safe feature builder, analog_v1 and lgbm_q_v1 (§7.6) with a walk-forward harness
grouped by season. Assume leakage if skill looks too good, and run the time-travel test to check.
```

## Week 7 — M7 finish
```
Start M7.2–M7.3. Add conformalized quantile regression (lgbm_q_cqr_v1), reliability diagrams, PIT histograms
and a CRPSS-vs-climatology table. Promote all models into the daily ledger as separate model_ids.
Never overwrite earlier ledger rows.
```

## Week 8 — Buffer
```
Buffer week. No new features. Raise coverage to the §11 targets, fix flaky tests, fill missing docs/methods
notes, and list tech debt in docs/PROGRESS.md ranked by risk.
```

---

## Week 9 — M8 Conditioned pricing · M9 Greeks
```
Start M8 and M9.1. Implement forecast-conditioned pricing via quantile mapping (§7.7) with a fair-value band,
and plot band width vs time. Then implement delta/gamma/theta with common random numbers and assert
Greek standard error < 5% of value. Label them "model sensitivities".
```

## Week 10 — M9 Hedge optimiser
```
Start M9.2–M9.3. Implement exposure templates, min-variance and CVaR95 (Rockafellar–Uryasev, cvxpy + HiGHS)
hedging with integer lots, order caps, position limits and margin budget (§7.9). Add property tests.
Build the synthetic Chennai delivery-rider case study and label it synthetic everywhere.
```

## Week 11 — M10 Basis · M11 Parametric & Scenarios
```
Start M10 and M11. Compute basis metrics per IMD grid cell (correlation, RMSE, Kendall tau, tail dependence,
hedge effectiveness) and export GeoJSON. Then build the parametric designer (§7.11) and scenario presets (§7.12).
```

---

## Week 12 — M12 API · live evaluation
```
Start M12. Implement every endpoint in §9.2 with the response envelope, problem+json errors, caching, rate limits,
and API keys. Export OpenAPI and generate TS types in web/lib/api with a CI drift check. Then score all ledger
forecasts so far (CRPS, coverage, PIT) and expose /v1/track-record.
```

## Week 13 — M13 Dashboard
```
Start M13. Read the frontend-design guidance if available. Build the 9 pages in §10 with Next.js 15, shadcn/ui,
ECharts and MapLibre. Every number needs a lineage hover, intervals always visible, no buy/sell colours, and
designed empty/stale states. Add Playwright smoke tests. Gate: Lighthouse ≥ 90.
```

## Week 14 — M14 Deploy
```
Start M14. Deploy the budget path (§4.1): Vercel, Fly.io or Render, Neon, R2. Move daily jobs to scheduled
GitHub Actions, add Sentry and backups, and write a deploy runbook in docs/. Tell me exactly which accounts
and secrets I must create. Never put secrets in the repo.
```

## Week 15 — M15 Launch
```
Start M15. Generate every paper figure via `make reproduce` on a clean clone. Draft the preprint in paper/
following §15. Update README with measured numbers only — leave [placeholders] for anything not measured.
Then walk through the Definition of Done (§18) step by step and report pass/fail.
```

---

## Utility prompts (use anytime)

**Stuck / bug**
```
Test X fails. Don't change the expected value. Find the root cause, show evidence, propose 2–3 hypotheses,
and wait for my choice.
```

**Leakage check**
```
Run the time-travel test for <date>: recompute features, forecast and valuation using only data available then,
and diff against the ledger row. Explain any difference.
```

**Skeptical quant review**
```
Act as a skeptical quant reviewer. List the 5 weakest assumptions in the current pipeline, with file/line
evidence and the expected impact on prices. Suggest tests to expose each one.
```

**Scope check**
```
Compare current progress with §13. Are we behind? If yes, apply the §14 time-crunch drop order and
show me the revised plan.
```

**Context reset**
```
Summarise this session into docs/PROGRESS.md (tasks done, measured numbers, open issues, next step)
and update the Current milestone in CLAUDE.md so the next session can resume.
```

**Commit hygiene**
```
Review uncommitted changes, split them into logical Conventional Commits, run make check, then commit.
```
