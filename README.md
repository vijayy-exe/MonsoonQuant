# MonsoonQuant

Prices, forecasts, explains and hedges India's exchange-traded rainfall futures (RAINCHNNAI, RAINMUMBAI).

A small, auditable quant-research platform — **not trading advice**.

Status: early scaffold (M0). See `docs/STATUS.md` for what's done and what's left, and `docs/SPEC.md` for the full build specification.

## Quickstart

```bash
make bootstrap   # uv sync, build C++ ext, pre-commit install
make check       # lint + types + tests
make dev         # docker compose up (db, mlflow)
mq --help
```

## Layout

See `docs/SPEC.md` §5 for the full repository layout rationale.
