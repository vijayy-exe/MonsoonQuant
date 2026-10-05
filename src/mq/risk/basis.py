"""Basis-risk engine (SPEC §7.10): for a candidate location (an IMD grid
cell within the city bounding box, or a user-dropped pin), how well does
the real CDR contract index track rainfall *at that specific point*
rather than at the two official stations it's actually defined on?

For each candidate cell, reconstructs a "local index" — the identical
CDR methodology (season-LPA anchor + cumulative deviation), applied to
a single-station proxy spec at that cell instead of the real 2-station
average — via a thin wrapper around `mq.pricing.burn.build_burn_sample`,
which already does exactly this reconstruction for the real stations.
Pairs the local series against the real official index series
(`mq.pricing.burn.build_burn_sample` on the real spec) year by year and
computes SPEC's six statistics.

**Hedge effectiveness here doubles as M9's hedge-optimiser building
block**: `1 - Var(L - h*X)/Var(L)` with `h* = Cov(L,X)/Var(X)` is
exactly the min-variance formula SPEC's `mq.risk.hedge` needs — this
module naturally produces the (local rain, contract index) joint
scenarios the hedge optimiser's own spec entry names as a prerequisite
("joint scenarios ... from basis engine"), treating the candidate
location's own rainfall as a *proxy* exposure (not a real one — no
"built-in exposure template" from SPEC §7.9 is attached here).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
from scipy import stats

from mq.pricing.burn import build_burn_sample
from mq.specs.contract import ContractSpec, StationRef


def local_index_series(
    spec: ContractSpec, rain_grid: pl.DataFrame, years: list[int], *, lat: float, lon: float
) -> dict[int, float]:
    """The real CDR methodology reconstructed for a single-station proxy
    at (lat, lon), sharing `spec`'s own period/LPA base period —
    `mq.pricing.burn.build_burn_sample` already does this reconstruction;
    this just points it at one candidate cell instead of the real
    stations."""
    proxy_spec = spec.model_copy(
        update={
            "stations": [StationRef(station_id="basis_cell", name="basis cell", lat=lat, lon=lon)]
        }
    )
    sample = build_burn_sample(proxy_spec, rain_grid, years)
    return dict(zip(sample.years, sample.payoffs, strict=True))


@dataclass(frozen=True)
class BasisStats:
    cell_lat: float
    cell_lon: float
    n_years: int
    correlation: float
    rmse: float
    kendall_tau: float
    tail_dependence_upper: float
    tail_dependence_lower: float
    seasonal_mismatch: float | None
    hedge_effectiveness: float
    hedge_ratio: float


def compute_basis_stats(
    local_values: dict[int, float],
    index_values: dict[int, float],
    *,
    tail_quantile: float = 0.8,
    local_daily: pl.DataFrame | None = None,
    index_daily: pl.DataFrame | None = None,
) -> BasisStats:
    """`local_values`/`index_values` are {year: season-final value}, as
    `local_index_series`/`build_burn_sample` produce. Only years present
    in BOTH are used — pairs, not two independent samples."""
    common_years = sorted(set(local_values) & set(index_values))
    if len(common_years) < 3:
        raise ValueError(
            f"need at least 3 common years to compute basis statistics, got {len(common_years)}"
        )
    local = np.array([local_values[y] for y in common_years])
    index = np.array([index_values[y] for y in common_years])

    correlation = float(np.corrcoef(local, index)[0, 1])
    rmse = float(np.sqrt(np.mean((local - index) ** 2)))
    kendall_tau = float(stats.kendalltau(local, index).statistic)

    n = len(common_years)
    local_rank = stats.rankdata(local) / (n + 1)
    index_rank = stats.rankdata(index) / (n + 1)
    index_upper = index_rank > tail_quantile
    index_lower = index_rank < (1 - tail_quantile)
    tail_upper = (
        float(np.mean(local_rank[index_upper] > tail_quantile))
        if index_upper.any()
        else float("nan")
    )
    tail_lower = (
        float(np.mean(local_rank[index_lower] < (1 - tail_quantile)))
        if index_lower.any()
        else float("nan")
    )

    var_index = float(np.var(index, ddof=1))
    if var_index == 0:
        hedge_ratio = 0.0
        hedge_effectiveness = 0.0
    else:
        hedge_ratio = float(np.cov(local, index, ddof=1)[0, 1] / var_index)
        residual = local - hedge_ratio * index
        var_local = float(np.var(local, ddof=1))
        hedge_effectiveness = (
            0.0 if var_local == 0 else 1.0 - float(np.var(residual, ddof=1)) / var_local
        )

    seasonal_mismatch = None
    if local_daily is not None and index_daily is not None:
        seasonal_mismatch = _seasonal_mismatch(local_daily, index_daily)

    return BasisStats(
        cell_lat=float("nan"),  # filled in by the caller (basis_grid), which knows the cell
        cell_lon=float("nan"),
        n_years=n,
        correlation=correlation,
        rmse=rmse,
        kendall_tau=kendall_tau,
        tail_dependence_upper=tail_upper,
        tail_dependence_lower=tail_lower,
        seasonal_mismatch=seasonal_mismatch,
        hedge_effectiveness=hedge_effectiveness,
        hedge_ratio=hedge_ratio,
    )


def _seasonal_mismatch(local_daily: pl.DataFrame, index_daily: pl.DataFrame) -> float:
    """1 - the mean within-season daily-rainfall correlation across
    shared years: do the two locations rain on the same DAYS, not just
    end up with similar season totals (which `correlation`/`rmse` above
    already cover). 0 = perfectly in sync day-to-day; 1 = no daily
    co-movement at all."""
    merged = local_daily.join(index_daily, on="date", how="inner", suffix="_index")
    if merged.height < 2:
        return float("nan")
    corr = merged.select(pl.corr("rain_mm", "rain_mm_index")).item()
    return float("nan") if corr is None else 1.0 - float(corr)


def basis_grid(
    spec: ContractSpec,
    rain_grid: pl.DataFrame,
    years: list[int],
    *,
    official_index_values: dict[int, float],
    lat_bounds: tuple[float, float],
    lon_bounds: tuple[float, float],
) -> list[BasisStats]:
    """One `BasisStats` per distinct grid cell already present in
    `rain_grid` within the given bounds — reuses the real grid's own
    cell locations rather than inventing an artificial step size, since
    `rain_grid` is already laid out on IMD's native 0.25° grid."""
    cells = (
        rain_grid.filter(
            (pl.col("lat") >= lat_bounds[0])
            & (pl.col("lat") <= lat_bounds[1])
            & (pl.col("lon") >= lon_bounds[0])
            & (pl.col("lon") <= lon_bounds[1])
        )
        .select("lat", "lon")
        .unique()
        .sort(["lat", "lon"])
    )
    results = []
    for cell_lat, cell_lon in cells.iter_rows():
        local_values = local_index_series(spec, rain_grid, years, lat=cell_lat, lon=cell_lon)
        try:
            cell_stats = compute_basis_stats(local_values, official_index_values)
        except ValueError:
            continue  # too few overlapping years for this cell -- skip, don't fabricate
        results.append(
            BasisStats(
                cell_lat=cell_lat,
                cell_lon=cell_lon,
                n_years=cell_stats.n_years,
                correlation=cell_stats.correlation,
                rmse=cell_stats.rmse,
                kendall_tau=cell_stats.kendall_tau,
                tail_dependence_upper=cell_stats.tail_dependence_upper,
                tail_dependence_lower=cell_stats.tail_dependence_lower,
                seasonal_mismatch=cell_stats.seasonal_mismatch,
                hedge_effectiveness=cell_stats.hedge_effectiveness,
                hedge_ratio=cell_stats.hedge_ratio,
            )
        )
    return results


def to_geojson(cells: list[BasisStats]) -> dict[str, object]:
    """GeoJSON FeatureCollection (SPEC's own stated output shape, for a
    MapLibre heatmap — the map rendering itself is M13 dashboard work,
    out of scope here)."""
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [c.cell_lon, c.cell_lat]},
            "properties": {
                "n_years": c.n_years,
                "correlation": c.correlation,
                "rmse": c.rmse,
                "kendall_tau": c.kendall_tau,
                "tail_dependence_upper": c.tail_dependence_upper,
                "tail_dependence_lower": c.tail_dependence_lower,
                "seasonal_mismatch": c.seasonal_mismatch,
                "hedge_effectiveness": c.hedge_effectiveness,
                "hedge_ratio": c.hedge_ratio,
            },
        }
        for c in cells
    ]
    return {"type": "FeatureCollection", "features": features}
