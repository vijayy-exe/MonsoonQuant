.PHONY: bootstrap check seed-registry test-golden bench ingest reproduce dev down \
	web-openapi web-codegen web-check web-e2e

# macOS + uv quirk: `uv run` creates/touches the editable-install .pth file
# with the UF_HIDDEN flag, which CPython 3.12's site.py silently skips,
# breaking `import mq` even right after chflags-ing it clear (uv re-applies
# the flag on its next startup). PYTHONPATH sidesteps site.py entirely and
# is unaffected. CI (Linux) never hits this — ext4 has no such flag. See
# docs/DECISIONS.md.
export PYTHONPATH := $(CURDIR)/src

bootstrap:
	uv sync
	cd web && pnpm install || true
	uv run pre-commit install

seed-registry:
	uv run mq specs seed-registry

check: seed-registry
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy --strict src/mq
	uv run pytest -q
	$(MAKE) seed-registry

test-golden:
	uv run pytest tests/golden -q

bench:
	uv run pytest tests/statistical -q -k bench

ingest:
	uv run mq run daily

reproduce:
	uv run mq research reproduce

dev:
	docker compose up -d

down:
	docker compose down

# M13 (dashboard, web/): the OpenAPI schema is exported straight from the
# live FastAPI app object (no server needed), then openapi-typescript
# turns it into web/lib/api/types.ts -- CI fails if this drifts from the
# API (SPEC §9's "CI fails if stale").
web-openapi:
	uv run python -c "\
import json; \
from mq.api.main import app; \
json.dump(app.openapi(), open('web/lib/api/openapi.json', 'w'), indent=2)"

web-codegen: web-openapi
	cd web && pnpm run codegen

web-check: web-codegen
	cd web && pnpm run lint
	cd web && pnpm run build

# Assumes `make dev`, a running `uvicorn mq.api.main:app`, and `pnpm dev`
# (or `pnpm build && pnpm start`) are already up -- E2E hits the real
# stack, never mocks (SPEC §11).
web-e2e:
	cd web && pnpm run test:e2e
