# Methods note: API foundation (M12, partial)

**Milestone:** M12 (SPEC §9). **Code:** `mq.api`.

## What this is

A real subset of SPEC's 18 listed `/v1` endpoints — each one backed by
an already-tested M1-M11 function, not a stub. Confirmed live: ran a
real `uvicorn` server and curled it (not just FastAPI's in-process
`TestClient`), and its auto-generated OpenAPI schema lists all 14 routes
correctly.

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

## 4. What's not done yet

Four of SPEC's 18 listed endpoints:

- `GET /v1/series/{id}/greeks` — unlike the other GETs, there is no
  `greeks` results table and no reusable "load real data, fit the chain
  model, compute Greeks" pipeline function; M9's real Greeks run was ad
  hoc scripting, never turned into production code. A real route here
  needs that pipeline built first (or a persistence table + a batch job
  to populate it), not a model fit live inside an HTTP request handler
  — real remaining work, not a thin route like the others were.
- `POST /v1/parametric/design`, `/v1/scenarios/run` — need request
  schemas plus SPEC's `n_paths` cap and 5s time-box. `parametric/design`
  is tractable the same way `hedge` was (`mq.risk.parametric` also
  operates on real historical scenario arrays, no simulator/model-fit
  needed — confirmed by reading its source, not assumed). `scenarios/run`
  may hit the same no-reusable-pipeline blocker as `greeks`, since M11's
  real scenario-lab run also used ad hoc `ChainModel` fitting — not yet
  checked.
- `GET /v1/track-record`, `/v1/lineage` — not started.

Also not done: Pydantic schema exports for OpenAPI→TS generation
(`openapi-typescript`), rate limiting, CORS to a real web origin (none
exists yet — M13), `web/lib/api/openapi.json` export (deliberately not
created yet — that path belongs under M13's own `web/` scaffold, not
manufactured ahead of it).
