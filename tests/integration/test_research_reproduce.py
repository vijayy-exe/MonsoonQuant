"""Real integration test for `mq research reproduce` (SPEC §17
Principle 10, M15) -- runs the actual figure-regeneration pipeline
against real local data and checks the real, measured numbers it
reports match the ones `docs/methods/*.md` and `docs/STATUS.md` cite,
not just that it doesn't crash."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mq.research.reproduce import reproduce_all
from mq.specs.specs_cli import seed_registry


@pytest.fixture(scope="module")
def figures(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    # test_registry_write.py's own teardown DELETEs RAINCHNNAI's
    # registration as part of exercising that same code path; within a
    # single `make check` pytest run this file sorts after it
    # alphabetically, so re-seed defensively rather than depend on
    # cross-file ordering.
    seed_registry()
    out_dir = tmp_path_factory.mktemp("figures")
    return reproduce_all(out_dir)


def _load(figures: dict[str, Path], name: str) -> dict:
    return json.loads(figures[name].read_text())


def test_burn_distribution_matches_the_real_documented_numbers(figures: dict[str, Path]) -> None:
    data = _load(figures, "burn_distribution")
    assert data["burn"]["n"] == 31
    assert data["burn"]["mean"] == pytest.approx(905.6, abs=0.5)
    assert data["burn"]["median"] == pytest.approx(843.4, abs=0.5)
    assert data["selected"] == "kde_cv"
    assert data["distribution_selection"]["kde_cv"]["mean_crps"] == pytest.approx(213.0, abs=0.5)


def test_forecasting_backtest_matches_the_real_documented_numbers(figures: dict[str, Path]) -> None:
    data = _load(figures, "forecasting_backtest")
    assert data["n_training_years"] == 31
    rungs = data["rungs"]
    assert rungs["clim_baseline"]["mean_crps"] == pytest.approx(156.44, abs=0.5)
    # M7's own real, honestly-reported finding: every newer rung
    # underperforms climatology at this sample size -- must still hold.
    for model_id in ["enso_clim_v1", "analog_v1", "lgbm_q_v1", "lgbm_q_cqr_v1"]:
        assert rungs[model_id]["mean_crps"] > rungs["clim_baseline"]["mean_crps"]


def test_hedge_case_study_hits_the_real_cvar_position_limit(figures: dict[str, Path]) -> None:
    """The real, structural finding (docs/methods/hedge.md §4): the
    real RAINCHNNAI index has been positive in every historical
    season, so an unconstrained-in-sign CVaR optimum doesn't exist for
    this contract -- the CVaR hedge must hit its own position-limit
    bound (20 lots here), not an interior optimum."""
    data = _load(figures, "hedge_case_study")
    assert data["n_years"] >= 2
    assert abs(data["cvar95"]["lots"]) == 20
    assert data["min_variance"]["lots"] < 0  # short, same real sign as the documented run


def test_parametric_case_study_reproduces_the_optimization_outcome(
    figures: dict[str, Path],
) -> None:
    """Reproduces docs/methods/parametric.md's real optimized
    trigger/slope/limit/premium exactly -- the basis-failure-
    probability figure itself does NOT currently reproduce (a real,
    documented discrepancy, see that note's own §4), so this test
    deliberately doesn't assert on it."""
    data = _load(figures, "parametric_case_study")
    opt = data["optimized"]
    assert opt["trigger"] == pytest.approx(843.4, abs=0.5)
    assert opt["slope"] == pytest.approx(1.0)
    assert opt["limit"] == pytest.approx(10_000.0)
    assert opt["premium"] == pytest.approx(200.1, abs=1.0)
    assert opt["converged"] is True


def test_basis_grid_matches_the_real_cell_count(figures: dict[str, Path]) -> None:
    data = _load(figures, "basis_grid")
    assert data["n_cells"] == 12
    correlations = [f["properties"]["correlation"] for f in data["geojson"]["features"]]
    assert max(correlations) >= 0.9  # real stations' own nearest cells
