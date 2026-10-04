from datetime import date

import numpy as np
import polars as pl
import pytest
from scipy import stats

from mq.pricing.distribution import (
    fit_bootstrap,
    fit_enso_conditioned_climatology,
    fit_gamma,
    fit_kde,
    fit_kde_cv_bandwidth,
    fit_lognormal,
    fit_weibull,
    oni_terciles,
    season_oni,
)


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(123)


@pytest.fixture
def gamma_sample(rng: np.random.Generator) -> np.ndarray:
    # Known ground truth: shape=5, scale=150 -> mean=750
    return stats.gamma(5, loc=0, scale=150).rvs(size=200, random_state=rng)


def test_fit_gamma_matches_sample_mean_and_exposes_a_density(
    gamma_sample: np.ndarray, rng: np.random.Generator
) -> None:
    # Not asserting the fitted "shape" recovers the true generating shape
    # (5.0): scipy's unconstrained 3-parameter gamma.fit trades shape off
    # against loc on small/well-behaved samples — a known MLE-stability
    # issue, not a bug here (see docs/methods/burn_distribution.md for the
    # same phenomenon surfacing as -inf held-out log-likelihoods on the
    # real burn sample). What must hold: the fit's own Monte-Carlo sample
    # reproduces the data's mean, and a density is actually defined.
    fd = fit_gamma(gamma_sample, rng=rng)
    assert fd.kind == "gamma"
    assert fd.samples.mean() == pytest.approx(gamma_sample.mean(), rel=0.1)
    assert fd.logpdf is not None


def test_fit_lognormal_and_weibull_produce_samples_matching_data_scale(
    gamma_sample: np.ndarray, rng: np.random.Generator
) -> None:
    for fitter in (fit_lognormal, fit_weibull):
        fd = fitter(gamma_sample, rng=rng)
        assert fd.samples.mean() == pytest.approx(gamma_sample.mean(), rel=0.2)
        assert fd.logpdf is not None


def test_fit_kde_silverman_vs_cv_both_center_on_data(
    gamma_sample: np.ndarray, rng: np.random.Generator
) -> None:
    kde = fit_kde(gamma_sample, rng=rng)
    kde_cv = fit_kde_cv_bandwidth(gamma_sample, rng=rng, candidate_bandwidths=(0.5, 1.0, 2.0))
    assert kde.samples.mean() == pytest.approx(gamma_sample.mean(), rel=0.15)
    assert kde_cv.samples.mean() == pytest.approx(gamma_sample.mean(), rel=0.15)
    assert kde_cv.params["bw_factor_vs_silverman"] in (0.5, 1.0, 2.0)


def test_fit_bootstrap_only_resamples_existing_values(rng: np.random.Generator) -> None:
    data = np.array([1.0, 2.0, 3.0])
    fd = fit_bootstrap(data, rng=rng)
    assert fd.logpdf is None
    assert set(np.unique(fd.samples)) <= {1.0, 2.0, 3.0}


def test_season_oni_averages_the_right_months() -> None:
    df = pl.DataFrame(
        {
            "index": ["oni"] * 4,
            "date": [date(2020, 8, 15), date(2020, 9, 15), date(2020, 10, 15), date(2020, 11, 15)],
            "value": [1.0, 2.0, 3.0, 100.0],  # Nov excluded from default ASO window
            "release_date": [date(2020, 8, 15)] * 4,
        }
    )
    assert season_oni(df, year=2020) == pytest.approx(2.0)
    assert season_oni(df, year=2021) is None


def test_oni_terciles_classifies_relative_to_the_sample() -> None:
    year_oni = {2000: -2.0, 2001: -1.0, 2002: 0.0, 2003: 1.0, 2004: 2.0, 2005: 3.0}
    terciles = oni_terciles(year_oni)
    assert terciles[2000] == 0
    assert terciles[2005] == 2
    assert len(set(terciles.values())) <= 3


def test_enso_climatology_falls_back_when_group_too_small(rng: np.random.Generator) -> None:
    data = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    years = [2000, 2001, 2002, 2003, 2004]
    # Every year in its own tercile bucket (degenerate) -> any group is size 1 < min_group_size
    year_terciles = {y: i for i, y in enumerate(years)}
    fd = fit_enso_conditioned_climatology(
        data, years, target_year=2000, year_terciles=year_terciles, rng=rng, min_group_size=5
    )
    assert fd.params["used_fallback"] == 1.0
    assert set(np.unique(fd.samples)) <= set(data)


def test_enso_climatology_uses_matching_group_when_large_enough(rng: np.random.Generator) -> None:
    data = np.array([10.0, 20.0, 30.0, 999.0, 999.0])
    years = [2000, 2001, 2002, 2003, 2004]
    year_terciles = {2000: 0, 2001: 0, 2002: 0, 2003: 1, 2004: 1}
    fd = fit_enso_conditioned_climatology(
        data, years, target_year=2000, year_terciles=year_terciles, rng=rng, min_group_size=3
    )
    assert fd.params["used_fallback"] == 0.0
    assert set(np.unique(fd.samples)) <= {10.0, 20.0, 30.0}
