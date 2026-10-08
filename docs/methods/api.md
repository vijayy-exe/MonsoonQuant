# Methods note: API foundation (M12, partial)

**Milestone:** M12 (SPEC §9). **Code:** `mq.api`.

## What this is

A real subset of SPEC's 18 listed `/v1` endpoints — each one backed by
an already-tested M1-M11 function, not a stub. Confirmed live: ran a
real `uvicorn` server and curled it (not just FastAPI's in-process
`TestClient`), and its auto-generated OpenAPI schema lists all 18 real
routes correctly (SPEC's own table lists `/v1/health`+`/v1/health/data`
as one row but they're two real routes, so 18 real routes = 17 of
SPEC's 18 table rows -- only `lineage` remains).

## 1. Built

| Method | Path | Backed by |
|---|---|---|
| GET | `/v1/health` | trivial liveness |
| GET | `/v1/health/data` | real row counts + latest dates from `index_values`, `market_quotes`, `prediction_ledger` |
| GET | `/v1/contracts` | the real `contracts` table (M1's `mq.specs.registry`) |
| GET | `/v1/contracts/{code}/spec` | the real `contract_specs` table (full resolved YAML) |
| GET | `/v1/series/{id}/valuation` | the real `valuations` table (M4's burn/dist writes) |
| GET | `/v1/series/{id}/valuations/compare` | same table, each method's own latest row |
| GET | `/v1/series/{id}/index` | the real `index_values` table (M3), newest-as_of-per-obs_date |
| GET | `/v1/series/{id}/quotes` | the real `market_quotes` table |
| GET | `/v1/series/{id}/mpr` | the real `mpr_estimates` table (M6) |
| GET | `/v1/series/{id}/forecast` | the real `prediction_ledger` rows (M7), scoped to one series' contract |
| GET | `/v1/series/{id}/basis` | a real, on-demand M10 basis-engine run — not a stored table |
| GET | `/v1/ledger` | the real `prediction_ledger` table |
| GET | `/v1/ledger/verify` | `mq.ledger.verify.verify_chain` directly, no new logic |
| POST | `/v1/hedge` | M9's real `min_variance_hedge`/`minimize_cvar_hedge`, against a real candidate location's real IMD rainfall and the real official index |
| POST | `/v1/parametric/design` | M11's real `optimize_cover`, same real location/exposure/index inputs as `hedge` |
| POST | `/v1/scenarios/run` | M11's real `run_scenario` against a real fitted M5.1/M5.2 chain model |
| GET | `/v1/series/{id}/greeks` | M9's real `delta`/`gamma`/`theta_*`, same real fitted chain model as `scenarios/run` |
| GET | `/v1/track-record` | M7's real 5-rung walk-forward backtest (`walk_forward_backtest`), re-run live, not stored |

Response envelope (`data`/`meta` with `as_of`/`data_version`/
`model_version`/`synthetic`/`disclaimer`) and RFC 9457 `problem+json`
errors (`mq/stale-data`, `mq/unknown-series`, `mq/infeasible-hedge`)
match SPEC §9.1 exactly.

## 2. Real findings from building against the real DB, not fixtures

**`valuations/compare`'s original design would have silently dropped a
method.** The first version joined on "whatever was written on the
same calendar day." Querying it against the real DB showed RAINCHNNAI's
burn and dist valuations were genuinely written a day apart (M4 ran
them in separate passes) — a same-day join returns only one method
whenever `as_of` isn't given. Fixed to return each method's own most
recent row instead, which is also the more useful semantic ("current
best estimate per method," not "whatever happened to land on the same
day").

**RAINCHNNAI's registration kept going missing — root-caused on the
3rd occurrence, not re-patched a 4th time.** `RAINCHNNAI-OCT26/NOV26/
DEC26` disappeared from `contracts`/`contract_specs` across three
separate sessions despite the Postgres container's own uptime ruling
out a container reset each time. The actual cause: `tests/integration/
test_registry_write.py` is a real, correctly-written test that
registers `RAINCHNNAI` (from the real spec YAML) and then, in its own
`finally: _cleanup()`, legitimately `DELETE`s every row under
`contract_code = 'RAINCHNNAI'` as teardown — including the real
"standing" registration, because this project runs all its tests
against one shared real database rather than per-test transactions or
a separate test DB (consistent with the project's own real-data-over-
fixtures discipline elsewhere). Nothing had ever made re-registering
RAINCHNNAI/RAINMUMBAI a repeatable setup step, so once that test ran
(as part of any `make check`, by any session), the real registration
stayed gone until someone happened to notice the API returning 404s
and manually re-ran the registry calls ad hoc — which is exactly what
happened, three times, before this was actually fixed at the root.

**Fix:** a new idempotent `mq specs seed-registry` CLI command
(`src/mq/specs/specs_cli.py`) that (re-)registers both real contracts'
specs and their real, documented listed series — `RAINCHNNAI` (Oct/Nov/
Dec 2026) and `RAINMUMBAI` (Jun/Jul/Aug/Sep 2026) — using today's date
for each series' active/expired status, so it's always correct
whenever it's actually run. Wired into `make check` both *before* the
test suite (so the DB starts from a known-good state regardless of what
a previous run left behind) and *after* it (so the DB is left correct
for anyone using the API immediately afterward, undoing whatever
`test_registry_write.py`'s own teardown just did). This is the kind of
fix the earlier two re-patches should have been — `register_contract_
spec`/`register_listed_series` were always idempotent upserts; what was
missing was making the call to them a permanent, repeatable part of the
project's own setup rather than a one-off script re-typed from memory
each time the symptom reappeared.

**`basis` was assumed cheap; measured, it wasn't.** The endpoint's
first draft claimed real computation was "well within a GET's latency
budget" based on M10's methods note describing "12 real cells" without
ever timing the actual API call. A live `uvicorn` smoke test's `curl`
hung past a 30s timeout; direct profiling found the real cause: a
31-year official burn-sample reconstruction (~8s) plus `basis_grid`'s
own real per-cell reconstruction loop (~39s for 12 cells) — **~48s
total**, not fast. Fixed with the same "cached by request hash" pattern
SPEC already prescribes for the three heavy POSTs: a process-lifetime
dict cache keyed by `(series_id, as_of, box_deg)`. Verified the cache
path actually runs, not just exists in the code — a test asserts the
second identical call is measurably faster (>5x) than the first, not
merely that both return `200`. Documented limitation: an in-process
dict cache doesn't share across multiple worker processes; a real
multi-worker deployment needs a shared cache (Redis, a DB table)
instead — noted here rather than silently assumed fine.

## 3. `POST /v1/hedge` — real optimiser, including a real degenerate-case reproduction

Request: `series_id`, a candidate `location_lat`/`location_lon`, one of
SPEC's four named exposure templates (+ optional kwargs), optional
`constraints` (mirrors `LotConstraints`), `alpha` (CVaR confidence),
optional `multiplier` (defaults to the contract spec's own resolved
value) and `as_of`. Computes the real official index (shared helper,
§2's `basis` pattern) and the real local CDR reconstruction at the
candidate location (`mq.risk.basis.local_index_series`), runs the
exposure template on the shifted-non-negative local values (the same
"illustrative simplification, stated as such" pattern
`.scratch/hedge_demo.py` and `docs/methods/hedge.md` already used), then
both real optimisers. Cached by request hash.

**Confirmed live that the API reproduces `docs/methods/hedge.md`'s own
documented structural finding, not just in a script.** Calling
`/v1/hedge` with no `constraints` lands `cvar95` at `LotConstraints`'
own 10,000-lot fallback with an extreme CVaR figure — the real,
mathematically correct answer when the real RAINCHNNAI index (positive
in all 31 historical seasons) gives the CVaR95 LP no interior optimum
to converge to. The endpoint does not sanitize or cap this; a test
asserts it happens, and a second test confirms passing `constraints`
(e.g. `max_order_lots`) avoids it.

## 4. `POST /v1/parametric/design` — real M11 optimizer, same real-data posture as hedge

Request mirrors `hedge`'s location/exposure-template shape, plus
`direction` (wet/dry), `budget`, `lam`/`loading` (Wang pricing), and
optional `trigger_grid`/`slope_grid`/`limit_grid`. Defaults
`loss_threshold` to the real loss sample's own P75 and `trigger_grid`
to 8 points from the real index's median to its max — the exact
restriction `docs/methods/parametric.md`'s real run used after finding
an unrestricted grid lets the optimizer find a degenerate near-always-
pay cover. Passing a `trigger_grid` that starts below the median would
reproduce that degenerate case; deliberately not guarded against, since
it's a legitimate optimum of the literal objective SPEC states, not a
bug (same posture the original M11 finding took). Includes an internal
self-consistency check: `optimize_cover`'s reported basis-failure
probability is recomputed independently from its own returned payout
and compared, raising if they disagree by more than float tolerance.
Cached by request hash.

## 5. `POST /v1/scenarios/run` — a real pipeline existed; an earlier assessment was wrong

This endpoint is the reason §4 of this note (written before it was
built) said `greeks`/`scenarios/run` needed "a real model-fitting
pipeline [that] doesn't exist yet" — **that claim was checked by
reading the source and was wrong**. `mq.pricing.simulator_glm.
fit_chain_model`, `mq.forecasting.features.station_average_daily_
series`, and `mq.pricing.simulator_glm.attach_monthly_covariate` are
already a complete, real, importable pipeline; what was actually
missing was a function wiring them together outside a one-off
`.scratch/scenarios_demo.py` script. That function is now
`mq.api.common.fit_real_chain_model`, timed directly: `fit_chain_model`
itself is fast (0.08s), the real cost is the daily-covariate-join prep
(~7s) — ~8s all-in, the same order as `hedge`/`basis`'s real cost, not
a missing capability.

The route: resolves `observed_to_date` from the real `index_values`
table when not given explicitly; calibrates `overdispersion_sd` against
the real official index's own observed season-to-season standard
deviation (`calibrate_overdispersion_sd`, a real root-find against real
data) rather than reusing the demo's hardcoded illustrative 0.336;
resolves `period_end` from the real `contracts` table; enforces SPEC's
`n_paths` ≤ 200k cap via the request schema itself. Two-tier caching:
the fitted model (keyed by `contract_code`/`as_of`, since it's identical
across every shock and every request against the same series/date) and
the full response (keyed by the complete request hash, SPEC's own
pattern). A real test confirms delta=1.0/gamma=0 under two different
ENSO shocks and that the real 2015 Chennai-analog shock pulls the real
2015 ONI/DMI values.

## 6. `GET /v1/series/{id}/greeks` — the last piece of the correction in §5

Built on the exact same `fit_real_chain_model` pipeline `scenarios/run`
uses, with its own small model-fit cache (not shared across modules,
same choice every other route made for its own cache). Query params
mirror `scenarios/run`'s real-data defaults: `observed_to_date` from
the latest real `index_values` row, `start_date` defaulting to the day
after `as_of`, `n_paths` capped at 200k. Omits theta entirely (rather
than erroring) when `start_date >= period_end`, since there's no
remaining season to bump a day into. A real test confirms delta=1.0/
gamma≈0 exactly — the same structural CDR-index finding
`docs/methods/greeks.md` already documented — now reproduced live
through the API, and that theta correctly reports `pairing="partial"`.

No request-hash response cache here (unlike the three heavy POSTs):
the model-fit cache already removes the dominant ~8s cost, and SPEC
doesn't name `greeks` among the endpoints requiring response caching.

## 7. `GET /v1/track-record` — a real live re-run, not a stored snapshot

Unlike `greeks`/`scenarios` (which reuse a cached fitted chain model)
and unlike `basis` (a stored-vs-live question that didn't apply to
M10), there's no `model_runs` row to read for this: M7's real 5-rung
backtest was reported in `docs/methods/forecasting.md` but never
persisted. Re-running it live is also the more honest design for a
"track record" endpoint — it should reflect current real data, not a
frozen historical snapshot.

Confirmed tractable the same way `scenarios/run` was: by actually
timing the real scripts (`.scratch/forecasting_backtest.py`, `.scratch/
lgbm_backtest.py`) before committing to the design — ~17s for
clim/enso/analog, ~29s for clim/lgbm/lgbm_cqr (clim_baseline shared
between runs), roughly the same order of cost as `basis`'s real ~48s.
Cached by `(contract_code, as_of)` (confirmed: ~38-47s uncached, ~0.01s
on a cache hit).

**Reproduces M7's exact real numbers, confirmed by a test, not just
plausible-looking ones**: a live call returns `mean_crps=156.44` for
`clim_baseline`, matching both the original real backtest run and two
independent fresh re-runs of the `.scratch` scripts this session. M7's
own honestly-reported finding — every newer rung (`enso_clim_v1`,
`analog_v1`, `lgbm_q_v1`, `lgbm_q_cqr_v1`) underperforms climatology at
n=31 seasons — is asserted to still hold, not hidden or retuned.

`RAINMUMBAI` isn't supported (`contract_code` defaults to
`RAINCHNNAI`) — its 2026 season is closed with no forecasting-ladder
training-row history, a real data-availability fact, not an
implementation gap.

## 8. What's not done yet

One of SPEC's 18 listed endpoints: `GET /v1/lineage` — not started.

Also not done: Pydantic schema exports for OpenAPI→TS generation
(`openapi-typescript`), rate limiting, CORS to a real web origin (none
exists yet — M13), `web/lib/api/openapi.json` export (deliberately not
created yet — that path belongs under M13's own `web/` scaffold, not
manufactured ahead of it).
