"""Statistical cross-check between the two simulator backends (SPEC
§7.4's own requirement for a NumPy reference to validate the C++ core
against). The two use different RNGs (NumPy's PCG64 vs. the C++ core's
Philox4x32-10) so outputs can never match bit-for-bit — this checks
that their *distributions* agree, at a sample size large enough that a
real implementation bug (wrong link function, wrong Gamma scale, a
swapped p01/p11) would show up far outside Monte Carlo noise.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl

from mq.index.lpa import DailyLPA
from mq.pricing import simulator, simulator_ref
from mq.pricing.simulator_glm import ChainModel, GLMFit

N_PATHS = 200_000
N_DAYS = 60


def _degenerate_model(*, mean_per_day: float, shape: float) -> ChainModel:
    always_wet = GLMFit(kind="logistic", coef=np.array([50.0]), n_obs=1, converged=True)
    amount = GLMFit(
        kind="gamma_log",
        coef=np.array([np.log(mean_per_day)]),
        n_obs=1,
        converged=True,
        extra={"shape": shape},
    )
    return ChainModel(
        n_harmonics=0,
        covariate_cols=[],
        occurrence_01=always_wet,
        occurrence_11=always_wet,
        amount=amount,
    )


def _flat_lpa(lpa_mm: float) -> DailyLPA:
    rows = [(m, d, lpa_mm) for m in range(1, 13) for d in range(1, 32)]
    table = pl.DataFrame(rows, schema=["month", "day", "lpa_mm"], orient="row")
    return DailyLPA(
        cell_lat=0.0,
        cell_lon=0.0,
        base_period_start_year=1991,
        base_period_end_year=2020,
        n_years_by_day={},
        table=table,
    )


def test_cpp_core_matches_numpy_reference_within_monte_carlo_noise() -> None:
    model = _degenerate_model(mean_per_day=10.0, shape=2.5)
    lpa = _flat_lpa(1.5)
    req = simulator_ref.SimRequest(
        n_paths=N_PATHS,
        start_date=date(2026, 9, 1),
        n_days=N_DAYS,
        seed=999,
        observed_to_date=50.0,
        start_state=1,
        covariates=[],
        overdispersion_sd=0.4,
    )

    ref_result = simulator_ref.simulate(model, lpa, req)
    cpp_result = simulator.simulate(model, lpa, req)

    ref_mean, ref_sd = ref_result.terminal_index.mean(), ref_result.terminal_index.std(ddof=1)
    cpp_mean, cpp_sd = cpp_result.terminal_index.mean(), cpp_result.terminal_index.std(ddof=1)

    # SE of the mean at this n is ~ sd/sqrt(n) ~ 256/447 ~ 0.57; allow a
    # generous 10-SE band so this isn't a flaky test, while still being
    # tight enough to catch a real model-wiring bug (which would be off
    # by a large multiple of the mean, not a fraction of a percent).
    se = ref_sd / np.sqrt(N_PATHS)
    assert abs(cpp_mean - ref_mean) < 10 * se
    assert abs(cpp_sd - ref_sd) / ref_sd < 0.05


def test_cpp_core_matches_numpy_reference_with_shape_below_one() -> None:
    # The real fitted wet-day amount shape (M5.1, nungambakkam) is
    # 0.316 — exercise the Gamma boost-trick branch on both backends.
    model = _degenerate_model(mean_per_day=8.0, shape=0.316)
    lpa = _flat_lpa(3.0)
    req = simulator_ref.SimRequest(
        n_paths=N_PATHS,
        start_date=date(2026, 9, 1),
        n_days=N_DAYS,
        seed=42,
        observed_to_date=0.0,
        start_state=0,
        covariates=[],
        overdispersion_sd=0.33,
    )

    ref_result = simulator_ref.simulate(model, lpa, req)
    cpp_result = simulator.simulate(model, lpa, req)

    ref_mean = ref_result.terminal_index.mean()
    cpp_mean = cpp_result.terminal_index.mean()
    se = ref_result.terminal_index.std(ddof=1) / np.sqrt(N_PATHS)
    assert abs(cpp_mean - ref_mean) < 10 * se
