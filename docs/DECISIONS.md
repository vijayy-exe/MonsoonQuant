# Decisions (ADR-lite)

Format per entry: decision, alternatives considered, reason, date.

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
