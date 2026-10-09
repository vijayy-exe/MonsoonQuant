"""Real integration test for `mq.forecasting.live.build_live_forecasts`
(M7's own stated live-row gap) -- the core logic behind `mq ledger
write-live`. Uses real RAINCHNNAI data for a known-good `as_of`
(2026-10-03, the last date real-time IMD/ONI/DMI data actually
covers), not synthetic fixtures -- the golden test for the underlying
`build_live_feature_row` (hand-computed, synthetic) already covers the
pure-logic edge cases; this covers the real end-to-end wiring plus
`write_forecast`'s idempotency guarantee on genuinely real rows."""

from __future__ import annotations

from datetime import date

from mq.api.common import BASIS_YEARS, load_climate_idx, load_combined_rain_grid, load_resolved_spec
from mq.db.session import session_scope
from mq.forecasting.live import build_live_forecasts
from mq.ledger.writer import write_forecast

AS_OF = date(2026, 10, 3)


def test_build_live_forecasts_returns_all_four_newer_rungs_with_real_data() -> None:
    with session_scope() as session:
        spec = load_resolved_spec(session, "RAINCHNNAI", "RAINCHNNAI")
    rain_grid = load_combined_rain_grid(AS_OF)
    climate_idx = load_climate_idx(AS_OF)

    forecasts = build_live_forecasts(
        spec,
        rain_grid,
        climate_idx,
        historical_years=BASIS_YEARS,
        as_of=AS_OF,
        data_version="test",
    )

    model_ids = {f.model_id for f in forecasts}
    assert model_ids == {"enso_clim_v1", "analog_v1", "lgbm_q_v1", "lgbm_q_cqr_v1"}
    for f in forecasts:
        assert f.contract_code == "RAINCHNNAI"
        assert f.as_of_date == AS_OF
        assert f.target == "remaining_rain_mm"
        assert f.fair_value is not None and f.fair_value > 0
        assert f.fair_value_lo90 is not None and f.fair_value_lo90 < f.fair_value
        assert f.fair_value_hi90 is not None and f.fair_value_hi90 > f.fair_value
        assert set(f.quantiles) == {"0.05", "0.25", "0.5", "0.75", "0.95"}


def test_write_forecast_is_idempotent_for_a_real_live_row() -> None:
    """These exact (RAINCHNNAI, 2026-10-03, analog_v1) rows were already
    written for real while building this feature -- re-running must be
    a safe no-op (SPEC §8.1), not a duplicate or an error."""
    with session_scope() as session:
        spec = load_resolved_spec(session, "RAINCHNNAI", "RAINCHNNAI")
    rain_grid = load_combined_rain_grid(AS_OF)
    climate_idx = load_climate_idx(AS_OF)

    forecasts = build_live_forecasts(
        spec,
        rain_grid,
        climate_idx,
        historical_years=BASIS_YEARS,
        as_of=AS_OF,
        data_version="test",
    )
    analog = next(f for f in forecasts if f.model_id == "analog_v1")
    # data_version differs from the real run's own -- write_forecast's
    # idempotency key is (contract_code, as_of_date, model_id,
    # model_version), not data_version, so this still exercises the
    # real skip path against the real row already in the ledger.
    assert write_forecast(analog) is None
