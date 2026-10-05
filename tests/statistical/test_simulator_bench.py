"""SPEC §7.4's benchmark acceptance: 1,000,000 paths x 92 days < 10s.
Run via `make bench` (pytest tests/statistical -k bench)."""

from __future__ import annotations

import platform
import time
from pathlib import Path

import mq_core_sim as core

N_PATHS = 1_000_000
N_DAYS = 92
BUDGET_SECONDS = 10.0


def test_one_million_paths_bench() -> None:
    params = core.SimParams()
    params.p01 = [0.25] * N_DAYS
    params.p11 = [0.55] * N_DAYS
    params.mean_amt = [8.0] * N_DAYS
    params.lpa_mm = [3.0] * N_DAYS
    params.shape = 0.316
    params.overdispersion_sd = 0.33

    req = core.SimRequest()
    req.n_paths = N_PATHS
    req.n_days = N_DAYS
    req.seed = 1
    req.observed_to_date = 0.0
    req.start_state = 0

    t0 = time.monotonic()
    core.simulate(params, req)
    elapsed = time.monotonic() - t0

    report = (
        f"{N_PATHS:,} paths x {N_DAYS} days: {elapsed:.3f}s "
        f"(budget {BUDGET_SECONDS}s, OpenMP={core.OPENMP_ENABLED}, cpu={platform.processor()})\n"
    )
    bench_dir = Path("docs/benchmarks")
    bench_dir.mkdir(parents=True, exist_ok=True)
    (bench_dir / "simulator_1m_paths.txt").write_text(report)

    assert elapsed < BUDGET_SECONDS, report
