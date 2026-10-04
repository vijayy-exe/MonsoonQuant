"""The CDR (Cumulative Deviation Rainfall) index engine (SPEC §7.2).

Implements the exact methodology from the official NCDEX product notes
(specs/sources/ncdex_product_note_rainchnnai_2026.yaml /
_rainmumbai_2026.yaml, Exhibit 2):

    Chennai_Daily_LPA(d)       = avg(station LPA(d) for each station)
    Chennai_Daily_Rainfall(d)  = avg(station rainfall(d) for each station)
    Chennai_Daily_Deviation(d) = Chennai_Daily_Rainfall(d) - Chennai_Daily_LPA(d)
    spot(period_start - 1)     = season LPA total (the "anchor point")
    spot(d)                    = spot(d-1) + Chennai_Daily_Deviation(d)

Pure function — no I/O. `rain_grid` must already be as_of-filtered by the
caller (via `mq.io.asof`) before being passed in; this module has no
look-ahead protection of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import polars as pl

from mq.index.lpa import DailyLPA, compute_daily_lpa, season_lpa_total
from mq.specs.contract import ContractSpec, LPARef, MonthDay
from mq.specs.loader import is_draft


@dataclass(frozen=True)
class IndexPath:
    contract_code: str
    as_of: date
    period_start: date
    period_end: date
    season_lpa_anchor: float
    dates: list[date]
    daily_rainfall_mm: list[float]
    daily_lpa_mm: list[float]
    daily_deviation_mm: list[float]
    spot: list[float]

    @property
    def observed_to_date(self) -> float:
        """The current CDR spot value as of `as_of` — what every pricing
        engine takes as its starting point for the remaining season."""
        return self.spot[-1] if self.spot else self.season_lpa_anchor


def _station_daily_rainfall(rain_grid: pl.DataFrame, *, lat: float, lon: float) -> pl.DataFrame:
    """This station's daily rainfall at its nearest grid cell — columns
    (date, rain_mm). Uses the same nearest-cell logic as the LPA module so
    both draw from the identical station proxy."""
    cell = (
        rain_grid.with_columns(
            ((pl.col("lat") - lat) ** 2 + (pl.col("lon") - lon) ** 2).alias("_dist2")
        )
        .sort("_dist2")
        .select("lat", "lon")
        .unique(maintain_order=True)
        .head(1)
    )
    if cell.height == 0:
        raise ValueError("rain_grid is empty — no cell to select")
    cell_lat, cell_lon = cell.row(0)
    return rain_grid.filter((pl.col("lat") == cell_lat) & (pl.col("lon") == cell_lon)).select(
        "date", "rain_mm"
    )


def compute_index(spec: ContractSpec, rain_grid: pl.DataFrame, as_of: date) -> IndexPath:
    """Reconstruct the CDR spot value for every day from the contract's
    period_start through min(as_of, period_end).

    Raises ValueError if the spec is still a draft, or if any station is
    missing rainfall data for a date in that window (a silent gap would
    corrupt every subsequent day's cumulative value — fail loudly instead,
    per SPEC §0.4's no-look-ahead/no-silent-gaps posture)."""
    if is_draft(spec):
        raise ValueError(f"cannot compute index from a draft spec: {spec.contract_code}")

    # is_draft() above guarantees none of these are still the "TODO_VERIFY"
    # sentinel — narrow the types explicitly so the rest of this function
    # can use them without a `Pending` union hanging over every access.
    if not isinstance(spec.index.period_start, MonthDay) or not isinstance(
        spec.index.period_end, MonthDay
    ):
        raise TypeError("expected a resolved period_start/period_end")
    if not isinstance(spec.stations, list):
        raise TypeError("expected a resolved station list")
    if not isinstance(spec.index.lpa, LPARef):
        raise TypeError("expected a resolved LPA reference")

    year = as_of.year
    period_start = date(year, spec.index.period_start.month, spec.index.period_start.day)
    period_end = date(year, spec.index.period_end.month, spec.index.period_end.day)
    if period_start > period_end:
        raise NotImplementedError("year-wrapping seasons are not supported")
    end_date = min(as_of, period_end)

    stations = spec.stations
    base_start, base_end = (
        spec.index.lpa.base_period_start_year,
        spec.index.lpa.base_period_end_year,
    )

    lpas: list[DailyLPA] = [
        compute_daily_lpa(
            rain_grid,
            lat=st.lat,
            lon=st.lon,
            base_period_start_year=base_start,
            base_period_end_year=base_end,
        )
        for st in stations
    ]
    season_lpa_anchor = sum(
        season_lpa_total(
            lpa,
            start_month=period_start.month,
            start_day=period_start.day,
            end_month=period_end.month,
            end_day=period_end.day,
        )
        for lpa in lpas
    ) / len(lpas)

    if end_date < period_start:
        return IndexPath(
            contract_code=spec.contract_code,
            as_of=as_of,
            period_start=period_start,
            period_end=period_end,
            season_lpa_anchor=season_lpa_anchor,
            dates=[],
            daily_rainfall_mm=[],
            daily_lpa_mm=[],
            daily_deviation_mm=[],
            spot=[],
        )

    window_dates = []
    d = period_start
    while d <= end_date:
        window_dates.append(d)
        d += timedelta(days=1)

    station_rainfall = [
        _station_daily_rainfall(rain_grid, lat=st.lat, lon=st.lon) for st in stations
    ]

    daily_rainfall: list[float] = []
    daily_lpa: list[float] = []
    missing: list[str] = []
    for day in window_dates:
        station_values = []
        for i, st_df in enumerate(station_rainfall):
            match = st_df.filter(pl.col("date") == day)
            if match.height == 0:
                missing.append(f"{stations[i].station_id} on {day.isoformat()}")
                continue
            station_values.append(float(match["rain_mm"].item()))
        if len(station_values) == len(stations):
            daily_rainfall.append(sum(station_values) / len(station_values))
        else:
            daily_rainfall.append(float("nan"))

        lpa_values = [
            lpa.table.filter((pl.col("month") == day.month) & (pl.col("day") == day.day))
            for lpa in lpas
        ]
        daily_lpa.append(sum(float(v["lpa_mm"].item()) for v in lpa_values) / len(lpa_values))

    if missing:
        raise ValueError(
            f"missing rainfall data for {len(missing)} station-day(s), e.g. {missing[:5]} — "
            "cannot compute a continuous CDR index with gaps"
        )

    deviations = [rain - lpa_val for rain, lpa_val in zip(daily_rainfall, daily_lpa, strict=True)]
    spot: list[float] = []
    running = season_lpa_anchor
    for dev in deviations:
        running += dev
        spot.append(running)

    return IndexPath(
        contract_code=spec.contract_code,
        as_of=as_of,
        period_start=period_start,
        period_end=period_end,
        season_lpa_anchor=season_lpa_anchor,
        dates=window_dates,
        daily_rainfall_mm=daily_rainfall,
        daily_lpa_mm=daily_lpa,
        daily_deviation_mm=deviations,
        spot=spot,
    )
