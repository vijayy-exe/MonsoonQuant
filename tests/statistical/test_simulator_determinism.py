"""SPEC §7.4's determinism requirement: same seed -> bit-identical
output regardless of OpenMP thread count. Run as subprocesses (not
threads within this pytest process) so OMP_NUM_THREADS actually takes
effect — OpenMP reads it once at the runtime's first parallel region,
which may already have been entered by the time a test tries to change
it in-process."""

from __future__ import annotations

import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent("""
    import hashlib
    import mq_core_sim as core
    import numpy as np

    params = core.SimParams()
    params.p01 = [0.25] * 92
    params.p11 = [0.55] * 92
    params.mean_amt = [8.0] * 92
    params.lpa_mm = [3.0] * 92
    params.shape = 0.316
    params.overdispersion_sd = 0.33

    req = core.SimRequest()
    req.n_paths = 100_000
    req.n_days = 92
    req.seed = 777
    req.observed_to_date = 0.0
    req.start_state = 0

    result = core.simulate(params, req)
    arr = np.asarray(result.terminal_index)
    print(hashlib.sha256(arr.tobytes()).hexdigest())
""")


def _run_with_threads(n_threads: int) -> str:
    import os

    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(n_threads)
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_same_seed_bit_identical_across_thread_counts() -> None:
    digests = {n: _run_with_threads(n) for n in (1, 2, 4, 8)}
    assert len(set(digests.values())) == 1, digests
