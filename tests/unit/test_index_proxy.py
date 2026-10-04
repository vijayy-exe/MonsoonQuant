from datetime import date

import pytest

from mq.index.engine import IndexPath
from mq.index.proxy import proxy_error


def _path() -> IndexPath:
    return IndexPath(
        contract_code="TESTCDR",
        as_of=date(2026, 9, 3),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 3),
        season_lpa_anchor=100.0,
        dates=[date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)],
        daily_rainfall_mm=[1.0, 2.0, 3.0],
        daily_lpa_mm=[1.0, 1.0, 1.0],
        daily_deviation_mm=[0.0, 1.0, 2.0],
        spot=[100.0, 101.0, 103.0],
    )


def test_proxy_error_computes_mean_and_max_abs_error() -> None:
    official = {
        date(2026, 9, 1): 100.0,  # exact match
        date(2026, 9, 2): 103.0,  # off by 2
        date(2026, 9, 3): 100.0,  # off by 3
    }
    report = proxy_error(_path(), official)
    assert report.n_obs == 3
    assert report.mean_abs_error == pytest.approx((0 + 2 + 3) / 3)
    assert report.max_abs_error == pytest.approx(3.0)
    assert report.mean_pct_lpa_error == pytest.approx(((0 + 2 + 3) / 3) / 100.0 * 100)


def test_proxy_error_only_uses_overlapping_dates() -> None:
    official = {date(2026, 9, 2): 101.0}  # exact match, only one date overlaps
    report = proxy_error(_path(), official)
    assert report.n_obs == 1
    assert report.mean_abs_error == pytest.approx(0.0)


def test_proxy_error_raises_when_no_overlap() -> None:
    official = {date(2099, 1, 1): 1.0}
    with pytest.raises(ValueError, match="no overlapping dates"):
        proxy_error(_path(), official)
