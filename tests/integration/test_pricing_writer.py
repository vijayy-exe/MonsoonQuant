from datetime import date

import numpy as np

from mq.db.models import Valuation
from mq.db.session import get_engine, session_scope
from mq.pricing.burn import BurnStats
from mq.pricing.distribution import FittedDistribution
from mq.pricing.writer import write_burn_valuation, write_distribution_valuation

TEST_SERIES = "TESTCDR-DEC26"


def _cleanup() -> None:
    with get_engine().connect() as conn:
        conn.exec_driver_sql(f"DELETE FROM valuations WHERE series_id = '{TEST_SERIES}'")
        conn.commit()


def test_write_burn_valuation_writes_mean_and_p5_p95_band() -> None:
    _cleanup()
    try:
        stats = BurnStats(
            n=10,
            mean=100.0,
            median=95.0,
            sd=20.0,
            p5=70.0,
            p25=85.0,
            p75=115.0,
            p95=140.0,
            skew=0.3,
            es_lower_5pct=65.0,
            es_upper_5pct=145.0,
        )
        write_burn_valuation(stats, series_id=TEST_SERIES, as_of_date=date(2026, 10, 4))

        with session_scope() as session:
            row = session.get(Valuation, (TEST_SERIES, date(2026, 10, 4), "burn", "P"))
            assert row is not None
            assert float(row.fair_value) == 100.0
            assert float(row.lo90) == 70.0
            assert float(row.hi90) == 140.0
            assert row.n_paths == 10
    finally:
        _cleanup()


def test_write_distribution_valuation_writes_sample_derived_fair_value() -> None:
    _cleanup()
    try:
        samples = np.linspace(0.0, 1000.0, 1001)  # uniform 0..1000, mean=500, p5=50, p95=950
        fd = FittedDistribution(kind="kde_cv", params={}, samples=samples, logpdf=None)
        write_distribution_valuation(
            fd, series_id=TEST_SERIES, as_of_date=date(2026, 10, 4), n_historical_seasons=31
        )

        with session_scope() as session:
            row = session.get(Valuation, (TEST_SERIES, date(2026, 10, 4), "dist", "P"))
            assert row is not None
            assert float(row.fair_value) == 500.0
            assert abs(float(row.lo90) - 50.0) < 1.0
            assert abs(float(row.hi90) - 950.0) < 1.0
            assert row.n_paths == 31
    finally:
        _cleanup()
