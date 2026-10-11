# Decisions (ADR-lite)

Format per entry: decision, alternatives considered, reason, date.

---

## 2026-10-05 — MLflow runs on host port 5001, not 5000

**Decision:** `docker-compose.yml` maps `5001:5000` for the `mlflow`
service; `MQ_MLFLOW_TRACKING_URI` and `.env.example` point at port 5001.

**Reason:** Same pattern as the Postgres 5433 decision (2026-10-04) — a
pre-existing service already owns the default port. Here it's macOS's own
AirPlay Receiver (ControlCenter), which binds port 5000 by default on
this machine and returns a bare `403 Forbidden` to any HTTP request
before it ever reaches Docker's port-forwarded container. Confirmed via
`lsof -nP -iTCP:5000 -sTCP:LISTEN` showing `ControlCenter` as the
listener, not Docker.

**Evidence:** `curl http://localhost:5000` and the mlflow Python client
both got 403 with no matching request in the mlflow container's own
gunicorn logs — the request never reached the app. After remapping to
5001, an actual mlflow run (`mlflow.start_run()`) succeeds.

---

## 2026-10-04 — Resolved VERIFY V1-V11 by finding the official NCDEX PDFs directly

**Decision:** Instead of waiting for the user to supply the NCDEX
contract-specification PDFs, searched for and downloaded them directly
from ncdex.com (Contract Specifications, Product Notes, launch circulars
for both RAINCHNNAI and RAINMUMBAI, plus the UDiFF bhavcopy format spec).
Registered all of them as hashed sources and rewrote both contract specs
from draft to fully resolved.

**Alternatives:** (a) keep waiting on the user; (b) proceed with the
proxy/draft values indefinitely.

**Reason:** The documents are NCDEX's own public downloads, linked
directly from their product pages (`ncdex.com/products/RAINCHNNAI` etc.)
— no login, no paywall, robots.txt allows everything. This is exactly
the kind of official primary source SPEC §0.3 wants cited, just reached by
searching rather than waiting to be handed. Found real values that
*corrected* an earlier guess: RAINCHNNAI's real period is Sep 1-Dec 31,
not the Oct 1 proxy used for the first ledger row.

**Verification note:** every numeric value placed in
`specs/contracts/*.yaml` is quoted or directly stated in a registered,
hashed source document — none of this is model-recalled background
knowledge about NCDEX being presented as sourced fact.

---

## 2026-10-04 — NCDEX's bhavcopy API is bot-gated; not worked around

**Decision:** `mq.pipelines.ncdex` ingests a manually-downloaded bhavcopy
CSV rather than fetching live. ncdex.com/markets/bhavcopy is a JS app
whose backend (`/api/bhavcopy`) is guarded by a fingerprint challenge —
the page's own served JS runs `Fingerprint.start("/__verify/fp",
"url=%2Fapi%2Fbhavcopy", ...)` before granting a `__hd_fingerprint`
cookie needed to call the API.

**Alternatives:** (a) script the fingerprint challenge (execute/replicate
the JS collection logic headlessly to mint a valid cookie); (b) use real
browser automation once available; (c) ingest manually-downloaded CSVs
for now.

**Reason:** (a) is deliberately defeating an anti-bot control the site
operator put there on purpose — the same category of action declined for
BoM/MJO earlier today, for the same reason. (b) wasn't available this
session (browser automation not connected). Chose (c): the
parser/normalizer/DQ pipeline is fully built and tested against the
*real* documented UDiFF schema, so a human (or a future legitimate
browser session) dropping a downloaded CSV into the pipeline is all
that's needed to go live — nothing architectural is blocked, only the
one automated-fetch step.

---

## 2026-10-04 — Proxy monsoon windows for `clim_v1`, pending VERIFY V3

**Decision:** Until the official NCDEX contract periods are known, use
Oct 1–Dec 31 (NE monsoon) as a labelled PROXY window for RAINCHNNAI and
Jun 1–Sep 30 (SW monsoon) for RAINMUMBAI, for climatology research only —
never presented as the real contract terms.

**Alternatives:** (a) invent no window at all and block clim_v1 entirely
until VERIFY V3 closes; (b) wait for the user to specify a window.

**Reason:** SPEC §2 itself states Chennai's NE monsoon runs roughly
October–December — that's not an invented value, it's the spec's own
framing, used here only to let the ledger go live in Week 1 as SPEC §2
explicitly asks for ("Critical Timing Insight"). Mumbai's SW-monsoon
window is general public meteorological knowledge, not a contract fact,
again used only as a research placeholder. Both are tagged `TODO_VERIFY`
in the real `ContractSpec.index.period_start/period_end` fields — this
proxy window lives only in the one-off script that called
`remaining_rain_climatology`, not in any spec file, so there's nothing to
accidentally treat as authoritative later.

**Consequence:** RAINMUMBAI gets no ledger row today because its proxy
season already closed (Sep 30) for 2026 — see docs/STATUS.md.

---

## 2026-10-04 — MJO (BoM) live ingestion deferred, not worked around

**Decision:** `mq.pipelines.climate_idx.fetch_mjo()` is implemented and
unit-tested against a real-format fixture, but not run live. BoM
(bom.gov.au) returns an explicit "Your access is blocked due to the
detection of a potential automated access request... does not support web
scraping" page for both the RMM data URL and their own anonymous-FTP help
page, from this network.

**Alternatives considered:** (a) spoof additional headers/TLS fingerprint
to get past the block; (b) try their anonymous FTP service; (c) defer.

**Reason:** (a) is evasion of an explicit anti-scraping control the site
operator stated outright — not something to route around quietly. (b)
their own help page recommending the FTP route is itself blocked from this
network, so it couldn't be verified as a way through either. Chose (c):
document the blocker, keep the parser ready, and let the user decide
(different network, BoM's registered-user service via
webreg@bom.gov.au, or just deprioritize MJO — it's the lowest-priority
of the three climate drivers for NE-monsoon forecasting per SPEC §3.1,
which calls out ONI and DMI first).

---

## 2026-10-04 — Dockerized Postgres runs on host port 5433, not 5432

**Decision:** `docker-compose.yml` maps `5433:5432` for the `postgres`
service; `MQ_DATABASE_URL` and `.env.example` point at port 5433.

**Alternatives:** (a) use port 5432 as the spec's example URL does; (b) stop
the machine's existing native Postgres to free 5432.

**Reason:** This machine already runs a Homebrew `postgresql@15` service
bound to `localhost:5432` (pre-existing, unrelated to this project — not
something to touch without being asked). Moving our container to 5433 avoids
any conflict or risk to that existing service.

---

## 2026-10-04 — Local Docker runtime is colima, not Docker Desktop

**Decision:** Use `colima start` to provide the Docker daemon.

**Alternatives:** Install Docker Desktop.

**Reason:** Docker Desktop.app is not installed on this machine; the `docker`
CLI (Homebrew) was already paired with `colima` as its backing VM. No need
to add another application when the existing setup works.

---

## 2026-10-04 — `make bootstrap`/Makefile exports `PYTHONPATH=$(CURDIR)/src`

**Decision:** The Makefile exports `PYTHONPATH` for every target rather than
relying solely on uv's editable install.

**Alternatives:** (a) rely on `uv sync`'s editable `.pth` file alone; (b)
`pip install -e .` outside uv; (c) chflags the `.pth` file before each run.

**Reason:** On this machine, `uv run` creates/touches the editable-install
`.pth` file (`_editable_impl_monsoonquant.pth`) with macOS's `UF_HIDDEN`
BSD flag set. CPython 3.12's `site.py` added logic (`addpackage`) that
silently **skips hidden `.pth` files**, so `import mq` fails even though the
package is "installed." Clearing the flag with `chflags nohidden` works for
exactly one invocation — the next `uv run` re-sets it during its own
startup, so a one-time fix doesn't stick. `PYTHONPATH` bypasses `site.py`
entirely and is unaffected by this. This is a macOS/APFS-specific quirk;
Linux CI runners have no such flag and are unaffected — do not port this
workaround into `.github/workflows/ci.yml`.

**Evidence:** `os.lstat` on the `.pth` file showed `st_flags` with
`UF_HIDDEN` (0x8000) set; CPython 3.12 `site.py`'s `addpackage` checks
`st_flags & stat.UF_HIDDEN` and returns early, logging
`"Skipping hidden .pth file"` under `_trace`.
