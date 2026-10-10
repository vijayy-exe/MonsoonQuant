from datetime import date

import numpy as np

from mq.db.models import MPREstimate
from mq.db.session import get_engine, session_scope
from mq.mpr.calibrate import CalibrationResult
from mq.mpr.uncertainty import BootstrapResult
from mq.mpr.writer import write_mpr_estimate

TEST_SERIES = "TESTCDR-DEC26"


def _cleanup() -> None:
    with get_engine().connect() as conn:
        conn.exec_driver_sql(f"DELETE FROM mpr_estimates WHERE series_id = '{TEST_SERIES}'")
        conn.commit()


def test_write_mpr_estimate_with_bootstrap_ci() -> None:
    _cleanup()
    try:
        result = CalibrationResult(param=0.0434, converged=True, price_at_param=920.0, settle=920.0)
        boot = BootstrapResult(
            samples=np.array([0.0, 0.05, 0.1]),
            median=0.0434,
            lo90=-0.3059,
            hi90=0.5105,
            n_bootstrap=500,
        )
        write_mpr_estimate(
            result,
            series_id=TEST_SERIES,
            as_of_date=date(2026, 10, 6),
            transform="wang",
            days_to_expiry=87,
            volume=0,
            open_interest=0,
            bootstrap=boot,
        )

        with session_scope() as session:
            row = session.get(MPREstimate, (TEST_SERIES, date(2026, 10, 6), "wang"))
            assert row is not None
            assert float(row.lambda_) == 0.0434
            assert float(row.ci_lo) == -0.3059
            assert float(row.ci_hi) == 0.5105
            assert row.method_ci == "bootstrap"
            assert row.days_to_expiry == 87
            assert row.volume == 0
            assert row.n_obs == 1
    finally:
        _cleanup()


def test_write_mpr_estimate_without_bootstrap_has_no_ci() -> None:
    _cleanup()
    try:
        result = CalibrationResult(param=0.02, converged=True, price_at_param=912.0, settle=912.0)
        write_mpr_estimate(
            result,
            series_id=TEST_SERIES,
            as_of_date=date(2026, 10, 5),
            transform="esscher",
            days_to_expiry=26,
            volume=0,
            open_interest=0,
        )

        with session_scope() as session:
            row = session.get(MPREstimate, (TEST_SERIES, date(2026, 10, 5), "esscher"))
            assert row is not None
            assert row.ci_lo is None
            assert row.ci_hi is None
            assert row.method_ci is None
    finally:
        _cleanup()
