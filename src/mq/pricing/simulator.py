"""The production chain-dependent rainfall simulator (SPEC §7.4, F10,
M5.3): same inputs/outputs as `mq.pricing.simulator_ref.simulate`, but
runs the inner Monte Carlo loop on the compiled `mq_core_sim` C++ core
(Philox4x32-10 RNG, OpenMP over paths) instead of a pure-NumPy loop.

Use this module for production pricing; `simulator_ref` stays as the
independent NumPy reference SPEC calls for ("Python reference
implementation in NumPy for statistical cross-checks") — the two are
verified to agree statistically in
tests/statistical/test_simulator_parity.py, and `mq_core_sim`'s own
determinism (same seed -> bit-identical output regardless of OpenMP
thread count) is verified in tests/statistical/test_simulator_determinism.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import mq_core_sim as _core
import numpy as np

from mq.index.lpa import DailyLPA
from mq.pricing.simulator_features import build_daily_arrays
from mq.pricing.simulator_glm import ChainModel
from mq.pricing.simulator_ref import SimRequest


@dataclass(frozen=True)
class SimResult:
    terminal_index: np.ndarray
    seasonal_total_mm: np.ndarray


def simulate(model: ChainModel, daily_lpa: DailyLPA, request: SimRequest) -> SimResult:
    arrays = build_daily_arrays(
        model,
        daily_lpa,
        start_date=request.start_date,
        n_days=request.n_days,
        covariates=request.covariates,
    )

    params = _core.SimParams()
    params.p01 = arrays.p01.tolist()
    params.p11 = arrays.p11.tolist()
    params.mean_amt = arrays.mean_amt.tolist()
    params.lpa_mm = arrays.lpa_mm.tolist()
    params.shape = model.amount.extra["shape"]
    params.overdispersion_sd = request.overdispersion_sd

    core_request = _core.SimRequest()
    core_request.n_paths = request.n_paths
    core_request.n_days = request.n_days
    core_request.seed = request.seed
    core_request.observed_to_date = request.observed_to_date
    core_request.start_state = request.start_state

    result = _core.simulate(params, core_request)
    return SimResult(
        terminal_index=np.asarray(result.terminal_index),
        seasonal_total_mm=np.asarray(result.seasonal_total_mm),
    )
