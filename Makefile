.PHONY: bootstrap check test-golden bench ingest reproduce dev down

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

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy --strict src/mq
	uv run pytest -q

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
