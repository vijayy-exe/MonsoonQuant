from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl
import pytest

from mq.index.lpa import DailyLPA
from mq.pricing.simulator_glm import ChainModel, GLMFit
from mq.risk.scenarios import (
    cloudburst,
    custom_shock,
    dry_november,
    el_nino,
    historical_analog,
    la_nina,
    negative_iod,
    neutral_enso,
    positive_iod,
    run_scenario,
    standard_presets,
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


def _always_dry_model() -> ChainModel:
    # covariate_cols=["oni","dmi"] (not empty) -- matches the [oni, dmi]
    # convention run_scenario's shock-application logic assumes, with
    # coef=0 for both so the oni/dmi VALUES don't matter to this
    # deterministic fixture's occurrence/amount outputs.
    never_wet = GLMFit(kind="logistic", coef=np.array([-50.0, 0.0, 0.0]), n_obs=1, converged=True)
    amount = GLMFit(
        kind="gamma_log",
        coef=np.array([0.0, 0.0, 0.0]),
        n_obs=1,
        converged=True,
        extra={"shape": 1.0},
    )
    return ChainModel(
        n_harmonics=0,
        covariate_cols=["oni", "dmi"],
        occurrence_01=never_wet,
        occurrence_11=never_wet,
        amount=amount,
    )


def test_preset_factories_set_expected_overrides() -> None:
    assert el_nino(oni=2.5).oni_override == pytest.approx(2.5)
    assert la_nina(oni=-1.8).oni_override == pytest.approx(-1.8)
    assert neutral_enso().oni_override == pytest.approx(0.0)
    assert positive_iod(dmi=0.9).dmi_override == pytest.approx(0.9)
    assert negative_iod(dmi=-0.9).dmi_override == pytest.approx(-0.9)
    assert cloudburst(bump_mm=150.0).observed_to_date_bump_mm == pytest.approx(150.0)
    dn = dry_november()
    assert dn.oni_override is not None and dn.dmi_override is not None


def test_custom_shock_builds_arbitrary_scenario() -> None:
    shock = custom_shock(name="my_shock", description="test", oni=1.2, dmi=-0.3, bump_mm=5.0)
    assert shock.name == "my_shock"
    assert shock.oni_override == pytest.approx(1.2)
    assert shock.dmi_override == pytest.approx(-0.3)
    assert shock.observed_to_date_bump_mm == pytest.approx(5.0)


def test_standard_presets_returns_seven_scenarios() -> None:
    presets = standard_presets()
    names = {p.name for p in presets}
    assert len(presets) == 7
    assert {
        "el_nino",
        "la_nina",
        "neutral_enso",
        "positive_iod",
        "negative_iod",
        "dry_november",
        "cloudburst",
    } == names


def test_historical_analog_uses_real_climate_idx_values() -> None:
    climate_idx = pl.DataFrame(
        {
            "index": ["oni", "dmi", "oni", "dmi"],
            "date": [date(2015, 9, 15), date(2015, 9, 15), date(2016, 9, 15), date(2016, 9, 15)],
            "value": [2.01, 0.5, -0.3, -0.1],
            "release_date": [date(2026, 1, 1)] * 4,
        }
    )
    shock = historical_analog(climate_idx, year=2015, month=9)
    assert shock.oni_override == pytest.approx(2.01)
    assert shock.dmi_override == pytest.approx(0.5)
    assert shock.is_historical_analog is True
    assert "2015" in shock.name


def test_historical_analog_raises_when_no_data() -> None:
    climate_idx = pl.DataFrame(
        {"index": [], "date": [], "value": [], "release_date": []},
    ).cast({"index": pl.Utf8, "date": pl.Date, "value": pl.Float64, "release_date": pl.Date})
    with pytest.raises(ValueError, match="no real ONI/DMI"):
        historical_analog(climate_idx, year=2015, month=9)


def test_run_scenario_cloudburst_shifts_valuation_by_exact_bump() -> None:
    # always-dry model -> terminal_index = obs - const, purely additive
    # in obs -> a +100mm cloudburst bump must shift simulator_mean by
    # EXACTLY +100mm, and delta/gamma stay exactly 1.0/0.0 regardless.
    model = _always_dry_model()
    lpa = _flat_lpa(2.0)
    common_kwargs = dict(
        observed_to_date=500.0,
        start_date=date(2026, 9, 1),
        period_end=date(2026, 9, 10),
        start_state=0,
        covariates=[0.0, 0.0],
        overdispersion_sd=0.0,
        n_paths=50,
        seed=1,
    )

    baseline = run_scenario(
        model, lpa, custom_shock(name="noop", description="no shock"), **common_kwargs
    )
    shocked = run_scenario(model, lpa, cloudburst(bump_mm=100.0), **common_kwargs)

    assert shocked.valuations["simulator_mean"] - baseline.valuations[
        "simulator_mean"
    ] == pytest.approx(100.0, abs=1e-6)
    assert shocked.greeks["delta"] == pytest.approx(1.0, abs=1e-9)
    assert shocked.greeks["gamma"] == pytest.approx(0.0, abs=1e-9)
    assert "theta_no_rain_day" in shocked.greeks


def test_run_scenario_computes_hedge_pnl_when_position_given() -> None:
    model = _always_dry_model()
    lpa = _flat_lpa(2.0)
    result = run_scenario(
        model,
        lpa,
        neutral_enso(),
        observed_to_date=500.0,
        start_date=date(2026, 9, 1),
        period_end=date(2026, 9, 10),
        start_state=0,
        covariates=[0.0, 0.0],
        overdispersion_sd=0.0,
        n_paths=50,
        seed=1,
        hedge_lots=-5,
        hedge_multiplier=50.0,
    )
    expected_pnl = -5 * 50.0 * result.valuations["simulator_mean"]
    assert result.hedge_pnl == pytest.approx(expected_pnl)
    assert result.hedge_pnl_note != ""


def test_run_scenario_without_hedge_position_leaves_pnl_none() -> None:
    model = _always_dry_model()
    lpa = _flat_lpa(2.0)
    result = run_scenario(
        model,
        lpa,
        neutral_enso(),
        observed_to_date=500.0,
        start_date=date(2026, 9, 1),
        period_end=date(2026, 9, 10),
        start_state=0,
        covariates=[0.0, 0.0],
        overdispersion_sd=0.0,
        n_paths=50,
        seed=1,
    )
    assert result.hedge_pnl is None
