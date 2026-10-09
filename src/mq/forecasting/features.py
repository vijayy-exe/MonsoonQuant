"""Shared (season, issue-day) training-row builder for the forecasting
ladder (SPEC §7.6): "every (season, issue-day) pair as a row" — one row
per historical calendar day within a contract's season, carrying the
features available at that issue date and the target it's trying to
predict. `enso_clim_v1`, `analog_v1`, and the LightGBM rungs all train
on this same table rather than building their own, so a change to how a
feature is computed can't silently diverge between rungs.

**Station scope**: averages both CDR stations' daily rainfall (mirrors
`mq.index.engine`'s own station averaging) rather than a single
representative station — more faithful to the real contract than a
single-station proxy would be. `clim_v1` (SPEC's Week-1 rung, already
ledger-live) used a single station when it was built; it's left as-is
per SPEC's "never modify ledger rows without asking" — this module's
2-station-averaged series is used for every *new* rung (including a
climatology baseline recomputed consistently with them for fair
backtest comparison), not retroactively for clim_v1's existing ledger
rows.

**Target**: remaining-period rainfall (raw mm, not CDR deviation) from
the issue date through period_end — the same quantity `clim_v1` already
forecasts (its window sums raw `rain_mm`, not deviation), so every rung
stays on a directly comparable scale for the CRPSS-vs-clim_v1 metric
SPEC requires.

**Features**: observed-to-date CDR deviation (how far this season's
rain has already diverged from the LPA pace — reuses
`mq.index.engine.compute_index`'s own cumulative-deviation
computation, not a reimplementation), ONI, DMI (MJO omitted — still
bot-gate-blocked, same decision as M5.1/M6), and days-remaining in the
season (the model's only direct signal of "how much season is left to
average out").
"""

from __future__ import annotations

from datetime import date

import polars as pl

from mq.io.grid import nearest_cell
from mq.specs.contract import ContractSpec, LPARef, MonthDay, StationRef


def station_average_daily_series(
    rain_grid: pl.DataFrame, stations: list[StationRef]
) -> pl.DataFrame:
    """Daily rainfall averaged across `stations`' nearest grid cells —
    columns (date, rain_mm), sorted by date. The same averaging
    `mq.index.engine` does internally for the real CDR index, exposed
    here as a standalone series for forecasting-feature use."""
    per_station = []
    for st in stations:
        cell_lat, cell_lon = nearest_cell(rain_grid, lat=st.lat, lon=st.lon)
        series = rain_grid.filter((pl.col("lat") == cell_lat) & (pl.col("lon") == cell_lon)).select(
            "date", pl.col("rain_mm").alias(f"_rain_{st.station_id}")
        )
        per_station.append(series)

    merged = per_station[0]
    for series in per_station[1:]:
        merged = merged.join(series, on="date", how="inner")
    rain_cols = [c for c in merged.columns if c != "date"]
    return merged.select("date", pl.mean_horizontal(rain_cols).alias("rain_mm")).sort("date")


def _climatological_daily_mean(
    series: pl.DataFrame, *, base_period_start_year: int, base_period_end_year: int
) -> pl.DataFrame:
    """The (month, day) -> mean-rain_mm table for an already-single
    (date, rain_mm) series — the same climatological-mean definition
    `mq.index.lpa.compute_daily_lpa` uses, minus its grid/nearest-cell
    lookup (not needed here: `series` is already one averaged daily
    series, not a multi-cell grid). LPA is linear in the underlying
    per-station series, so this table equals the average of each
    station's own LPA table — computing it directly on the
    already-averaged series is equivalent, and far cheaper."""
    base = series.filter(
        (pl.col("date").dt.year() >= base_period_start_year)
        & (pl.col("date").dt.year() <= base_period_end_year)
    ).with_columns(pl.col("date").dt.month().alias("month"), pl.col("date").dt.day().alias("day"))
    base = base.filter(~((pl.col("month") == 2) & (pl.col("day") == 29)))
    return base.group_by(["month", "day"]).agg(pl.col("rain_mm").mean().alias("lpa_mm"))


def build_training_rows(
    spec: ContractSpec,
    rain_grid: pl.DataFrame,
    climate_idx: pl.DataFrame,
    years: list[int],
) -> pl.DataFrame:
    """One row per (year, issue_date) for every issue_date in
    [period_start, period_end) of `year` — period_end itself is excluded
    since there is no "remaining" rain left to forecast on the last day.
    Years without full season coverage in `rain_grid` are silently
    skipped (same posture as `mq.pricing.burn.build_burn_sample`: a
    real backfill gap should drop a year, not be guessed around).

    Columns: year, issue_date, issue_month, issue_day, days_remaining,
    observed_to_date_anomaly_mm, oni, dmi, target_remaining_rain_mm.
    """
    if not isinstance(spec.index.period_start, MonthDay) or not isinstance(
        spec.index.period_end, MonthDay
    ):
        raise TypeError("expected a resolved period_start/period_end")
    if not isinstance(spec.stations, list):
        raise TypeError("expected a resolved station list")
    if not isinstance(spec.index.lpa, LPARef):
        raise TypeError("expected a resolved LPA reference")

    avg_series = station_average_daily_series(rain_grid, spec.stations)
    lpa_table = _climatological_daily_mean(
        avg_series,
        base_period_start_year=spec.index.lpa.base_period_start_year,
        base_period_end_year=spec.index.lpa.base_period_end_year,
    )

    season_frames = []
    for year in years:
        period_start = date(year, spec.index.period_start.month, spec.index.period_start.day)
        period_end = date(year, spec.index.period_end.month, spec.index.period_end.day)
        season = avg_series.filter(
            (pl.col("date") >= period_start) & (pl.col("date") <= period_end)
        ).sort("date")
        expected_days = (period_end - period_start).days + 1
        if season.height != expected_days:
            continue  # incomplete season coverage -- skip, don't guess

        season = season.with_columns(
            pl.col("date").dt.month().alias("month"), pl.col("date").dt.day().alias("day")
        ).join(lpa_table, on=["month", "day"], how="left")
        if season["lpa_mm"].null_count() > 0:
            raise ValueError(
                f"year {year}: missing LPA value for a calendar day inside the season window "
                "-- a real gap in the base-period table, not something to guess past"
            )

        total_rain = float(season["rain_mm"].sum())
        season = season.with_columns(
            pl.lit(year).alias("year"),
            (pl.col("rain_mm") - pl.col("lpa_mm")).cum_sum().alias("observed_to_date_anomaly_mm"),
            (pl.lit(total_rain) - pl.col("rain_mm").cum_sum()).alias("target_remaining_rain_mm"),
            (pl.lit(period_end) - pl.col("date")).dt.total_days().alias("days_remaining"),
        )
        season_frames.append(
            season.filter(pl.col("date") < pl.lit(period_end)).select(
                "year",
                pl.col("date").alias("issue_date"),
                pl.col("month").alias("issue_month"),
                pl.col("day").alias("issue_day"),
                "days_remaining",
                "observed_to_date_anomaly_mm",
                "target_remaining_rain_mm",
            )
        )

    if not season_frames:
        raise ValueError("no training rows could be built -- check data coverage for `years`")
    rows = pl.concat(season_frames)
    rows = _join_oni_dmi(rows, climate_idx)
    if rows.height == 0:
        raise ValueError("no training rows could be built -- no ONI/DMI coverage for `years`")
    return rows


def _join_oni_dmi(rows: pl.DataFrame, climate_idx: pl.DataFrame) -> pl.DataFrame:
    """Shared by `build_training_rows` and `build_live_feature_row` so
    the two can never silently diverge on how ONI/DMI get attached."""
    covariates = (
        climate_idx.filter(pl.col("index").is_in(["oni", "dmi"]))
        .with_columns(
            pl.col("date").dt.year().alias("cov_year"), pl.col("date").dt.month().alias("cov_month")
        )
        .pivot(on="index", index=["cov_year", "cov_month"], values="value")
    )
    return rows.join(
        covariates,
        left_on=["year", "issue_month"],
        right_on=["cov_year", "cov_month"],
        how="inner",  # drop rows whose issue-month has no ONI/DMI coverage
    )


def build_live_feature_row(
    spec: ContractSpec,
    rain_grid: pl.DataFrame,
    climate_idx: pl.DataFrame,
    as_of: date,
) -> pl.DataFrame:
    """One row of real, live features for `as_of`'s own in-progress
    season (SPEC §7's own stated gap, M7: "needs a separate live-row
    builder for the in-progress season"). `build_training_rows` can
    never produce this row -- it structurally requires a *complete*
    season, which the current one, by definition, isn't yet.

    Same schema as `build_training_rows`' output (so the two concatenate
    directly for a live forecast call), except `target_remaining_rain_mm`
    is NaN: genuinely unknown until the season closes, and never read by
    any rung's live-prediction path (`analog_forecast`,
    `enso_conditioned_remaining_rain_forecast`, and the LightGBM rungs'
    prediction step all read only the feature columns off the target
    row -- confirmed by reading each, not assumed) -- only a
    walk-forward *backtest* reads it, and that never calls this
    function."""
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
    if not (period_start <= as_of < period_end):
        raise ValueError(
            f"as_of={as_of} is outside this contract's open season window "
            f"[{period_start}, {period_end}) for {year} -- nothing live to forecast"
        )

    avg_series = station_average_daily_series(rain_grid, spec.stations)
    lpa_table = _climatological_daily_mean(
        avg_series,
        base_period_start_year=spec.index.lpa.base_period_start_year,
        base_period_end_year=spec.index.lpa.base_period_end_year,
    )

    season_to_date = avg_series.filter(
        (pl.col("date") >= period_start) & (pl.col("date") <= as_of)
    ).sort("date")
    expected_days = (as_of - period_start).days + 1
    if season_to_date.height != expected_days:
        raise ValueError(
            f"{year}: missing daily rainfall between {period_start} and {as_of} -- "
            "a real data gap, not something to guess past"
        )

    season_to_date = season_to_date.with_columns(
        pl.col("date").dt.month().alias("month"), pl.col("date").dt.day().alias("day")
    ).join(lpa_table, on=["month", "day"], how="left")
    if season_to_date["lpa_mm"].null_count() > 0:
        raise ValueError(
            f"{year}: missing LPA value for a calendar day between {period_start} and {as_of}"
        )

    observed_to_date_anomaly_mm = float(
        (season_to_date["rain_mm"] - season_to_date["lpa_mm"]).sum()
    )
    days_remaining = (period_end - as_of).days

    row = pl.DataFrame(
        {
            "year": [year],
            "issue_date": [as_of],
            "issue_month": [as_of.month],
            "issue_day": [as_of.day],
            "days_remaining": [days_remaining],
            "observed_to_date_anomaly_mm": [observed_to_date_anomaly_mm],
            "target_remaining_rain_mm": [float("nan")],
        }
    )

    # Deliberately NOT `_join_oni_dmi`'s exact issue-month match: that's
    # correct for historical rows (every past month's ONI/DMI has long
    # since been published), but a real, found-not-assumed problem for
    # a LIVE row -- NOAA/BoM publish a month's ONI/DMI with a real lag
    # (confirmed directly: as of a 2026-10-03 `as_of`, ONI's own latest
    # published value was for 2026-08, not October). A live forecast
    # uses the most recently *published* value as of `as_of`, same as
    # any real operational system would have to.
    latest_covariates = (
        climate_idx.filter(pl.col("index").is_in(["oni", "dmi"]))
        .sort("date")
        .group_by("index")
        .last()
        .select("index", "value")
    )
    if latest_covariates.height < 2:
        raise ValueError(f"no published ONI/DMI value at all as of {as_of}")
    row = row.join(
        latest_covariates.filter(pl.col("index") == "oni").select(pl.col("value").alias("oni")),
        how="cross",
    ).join(
        latest_covariates.filter(pl.col("index") == "dmi").select(pl.col("value").alias("dmi")),
        how="cross",
    )
    return row
