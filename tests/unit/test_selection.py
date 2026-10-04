import numpy as np
import pytest
from scipy import stats

from mq.pricing.selection import CVResult, rolling_origin_cv, select_best_distribution


def test_select_best_distribution_picks_lowest_crps() -> None:
    results = {
        "gamma": CVResult(kind="gamma", n_folds=10, mean_crps=5.0, mean_log_likelihood=-2.0),
        "kde": CVResult(kind="kde", n_folds=10, mean_crps=3.0, mean_log_likelihood=None),
        "weibull": CVResult(kind="weibull", n_folds=10, mean_crps=4.0, mean_log_likelihood=-1.0),
    }
    assert select_best_distribution(results) == "kde"


def test_rolling_origin_cv_runs_all_candidates_without_oni() -> None:
    rng = np.random.default_rng(7)
    payoffs = stats.gamma(5, loc=0, scale=100).rvs(size=12, random_state=rng)
    years = list(range(2000, 2012))

    results = rolling_origin_cv(payoffs, years, oni=None, rng=rng)

    assert set(results.keys()) == {
        "gamma",
        "lognormal",
        "weibull",
        "kde_silverman",
        "kde_cv",
        "bootstrap",
    }
    for kind, r in results.items():
        assert r.n_folds == len(payoffs)
        assert r.mean_crps >= 0
        if kind == "bootstrap":
            assert r.mean_log_likelihood is None
        else:
            # log-likelihood can be -inf for a bounded-support fit on an
            # edge-case held-out value (a real, documented phenomenon —
            # see docs/methods/burn_distribution.md) but must be a float.
            assert r.mean_log_likelihood is None or isinstance(r.mean_log_likelihood, float)


def test_rolling_origin_cv_adds_enso_climatology_when_oni_supplied() -> None:
    from datetime import date

    import polars as pl

    rng = np.random.default_rng(7)
    payoffs = stats.gamma(5, loc=0, scale=100).rvs(size=12, random_state=rng)
    years = list(range(2000, 2012))
    oni_rows = []
    for i, y in enumerate(years):
        for m in (8, 9, 10):
            oni_rows.append(
                {
                    "index": "oni",
                    "date": date(y, m, 1),
                    "value": float(i % 3 - 1),
                    "release_date": date(y, m, 1),
                }
            )
    oni = pl.DataFrame(oni_rows)

    results = rolling_origin_cv(payoffs, years, oni=oni, rng=rng)
    assert "enso_climatology" in results
    assert results["enso_climatology"].n_folds == len(payoffs)


def test_select_best_distribution_raises_on_empty_dict() -> None:
    with pytest.raises(ValueError):
        select_best_distribution({})
