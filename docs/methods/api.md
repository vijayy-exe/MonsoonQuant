# Methods note: API foundation (M12, partial)

**Milestone:** M12 (SPEC §9). **Code:** `mq.api`.

## What this is

A real subset of SPEC's 18 listed `/v1` endpoints — each one backed by
an already-tested M1-M11 function, not a stub. Confirmed live: ran a
real `uvicorn` server and curled it (not just FastAPI's in-process
`TestClient`), and its auto-generated OpenAPI schema lists all 8 routes
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
| GET | `/v1/ledger` | the real `prediction_ledger` table |
| GET | `/v1/ledger/verify` | `mq.ledger.verify.verify_chain` directly, no new logic |

Response envelope (`data`/`meta` with `as_of`/`data_version`/
`model_version`/`synthetic`/`disclaimer`) and RFC 9457 `problem+json`
errors (`mq/stale-data`, `mq/unknown-series`, `mq/infeasible-hedge`)
match SPEC §9.1 exactly.

## 2. Two real findings from building against the real DB, not fixtures

**`valuations/compare`'s original design would have silently dropped a
method.** The first version joined on "whatever was written on the
same calendar day." Querying it against the real DB showed RAINCHNNAI's
burn and dist valuations were genuinely written a day apart (M4 ran
them in separate passes) — a same-day join returns only one method
whenever `as_of` isn't given. Fixed to return each method's own most
recent row instead, which is also the more useful semantic ("current
best estimate per method," not "whatever happened to land on the same
day").

**RAINCHNNAI's listed series were never registered in the `contracts`
table**, discovered while building the series-valuation endpoint's
existence check. Real burn/dist valuations and ledger rows existed for
`RAINCHNNAI-OCT26/NOV26/DEC26`, but the `contracts` table only had
RAINMUMBAI's four (now-expired) series — RAINCHNNAI's own
`register_listed_series` call from earlier work apparently never ran
for real, or ran against a database that was later reset. Fixed by
calling the already-built `mq.specs.registry.register_contract_spec`/
`register_listed_series` directly against the real database — a real
data-completeness fix, not a code change, and idempotent (safe to
re-run).

**This recurred on a later re-run of the same test suite** (same day,
container never restarted) — the Postgres container's uptime ruled out
a container reset, so the row loss has some other cause not yet
diagnosed (an open transaction never reaching `COMMIT`? a stray
rollback?). Re-applying the same two registry calls fixed it again and
this time was confirmed with a fresh DB connection after the fix. The
underlying one-off-script approach is fragile precisely because
there's no migration/seed step that's supposed to own this state —
worth turning into a proper idempotent seed command before relying on
it again.

## 3. What's not done yet

Ten of SPEC's 18 listed endpoints: `index`, `quotes`, `forecast`,
`greeks`, `mpr`, `basis` (GETs — all have real underlying functions
from M3/M5-M11, just not yet wired into routes), and the three heavy
POSTs (`hedge`, `parametric/design`, `scenarios/run` — need request
schemas plus the SPEC-mandated `n_paths` cap and 5s time-box), plus
`track-record` and `lineage`.

Also not done: Pydantic schema exports for OpenAPI→TS generation
(`openapi-typescript`), rate limiting, request caching, CORS to a real
web origin (none exists yet — M13), `web/lib/api/openapi.json` export
(deliberately not created yet — that path belongs under M13's own
`web/` scaffold, not manufactured ahead of it).
