"""analog_v1 — k-nearest past seasons (SPEC §7.6).

Third rung of the forecasting ladder: at a given issue date, find the
`k` historical years whose same-issue-day feature vector
(observed-to-date CDR anomaly, ONI, DMI) is closest to the target
year's, and report the empirical quantiles of THOSE years'
remaining-period rainfall. MJO is named in SPEC's feature list but
omitted here — still bot-gate-blocked (same decision as M5.1, M6, and
`enso_clim_v1`).

No new dependency: k-NN over 3 standardized features and at most a few
thousand rows is a handful of lines of NumPy (one pairwise-distance
computation), not something that needs scikit-learn.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl

FEATURE_COLS = ["observed_to_date_anomaly_mm", "oni", "dmi"]

MODEL_ID = "analog_v1"
MODEL_VERSION = "0.1.0"

QUANTILE_LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]


@dataclass(frozen=True)
class AnalogForecast:
    target_year: int
    issue_date: date
    k: int
    analog_years: list[int]
    distances: list[float]
    quantiles: dict[str, float]
    sample_values: list[float]


def analog_forecast(
    training_rows: pl.DataFrame,
    *,
    target_year: int,
    issue_date: date,
    k: int = 5,
) -> AnalogForecast:
    """Standardizes `FEATURE_COLS` using the *other* years' same-day
    rows (never the target's own feature scale — avoids the target
    year silently dominating the standardization when the sample is
    small), computes Euclidean distance in that standardized space, and
    takes the `k` nearest years' `target_remaining_rain_mm` as the
    forecast sample."""
    same_day = training_rows.filter(
        (pl.col("issue_month") == issue_date.month) & (pl.col("issue_day") == issue_date.day)
    )
    target_row = same_day.filter(pl.col("year") == target_year)
    if target_row.height == 0:
        raise ValueError(f"no training row for target_year={target_year} issue_date={issue_date}")

    other = same_day.filter(pl.col("year") != target_year)
    if other.height < k:
        raise ValueError(
            f"only {other.height} analog year(s) available, need k={k} -- "
            "reduce k or widen the training sample"
        )

    other_features = other.select(FEATURE_COLS).to_numpy()
    target_features = target_row.select(FEATURE_COLS).to_numpy()[0]

    mean = other_features.mean(axis=0)
    sd = other_features.std(axis=0, ddof=1)
    sd[sd == 0] = 1.0  # a constant feature contributes 0 to every distance either way

    other_z = (other_features - mean) / sd
    target_z = (target_features - mean) / sd

    distances = np.sqrt(np.sum((other_z - target_z) ** 2, axis=1))
    order = np.argsort(distances)[:k]

    analog_years = other["year"].to_numpy()[order].tolist()
    analog_distances = distances[order].tolist()
    samples = other["target_remaining_rain_mm"].to_numpy()[order]

    series = pl.Series(samples)
    quantiles: dict[str, float] = {}
    for q in QUANTILE_LEVELS:
        value = series.quantile(q, interpolation="linear")
        assert value is not None  # k>=1 guaranteed by the height check above
        quantiles[str(q)] = float(value)

    return AnalogForecast(
        target_year=target_year,
        issue_date=issue_date,
        k=k,
        analog_years=analog_years,
        distances=analog_distances,
        quantiles=quantiles,
        sample_values=samples.tolist(),
    )
