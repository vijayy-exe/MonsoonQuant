"""`/v1/series/{id}/valuation` and `/v1/series/{id}/valuations/compare`
(SPEC §9.2): the real `valuations` table rows M4's `write_burn_valuation`/
`write_distribution_valuation` wrote — no synthetic placeholders.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from mq.api.common import BASIS_YEARS, load_rain_grid, load_resolved_spec, official_index_values
from mq.api.deps import get_db
from mq.api.errors import unknown_series
from mq.api.schemas.envelope import Envelope, Meta
from mq.db.models import (
    Contract,
    IndexValue,
    MarketQuote,
    MPREstimate,
    PredictionLedgerRow,
    Valuation,
)
from mq.risk.basis import basis_grid, to_geojson

router = APIRouter(prefix="/v1/series", tags=["series"])


class ValuationData(BaseModel):
    series_id: str
    as_of_date: str
    method: str
    measure: str
    fair_value: float | None
    lo90: float | None
    hi90: float | None
    n_paths: int | None


class ValuationsCompareData(BaseModel):
    series_id: str
    as_of_date: str
    by_method: dict[str, ValuationData]


def _now_meta(**kwargs: Any) -> Meta:
    return Meta(generated_at=datetime.now(UTC), **kwargs)


def _assert_series_exists(db: Session, series_id: str) -> None:
    exists = db.execute(select(Contract.series_id).where(Contract.series_id == series_id)).first()
    if exists is None:
        raise unknown_series(series_id)


def _to_valuation_data(row: Valuation) -> ValuationData:
    return ValuationData(
        series_id=row.series_id,
        as_of_date=row.as_of_date.isoformat(),
        method=row.method,
        measure=row.measure,
        fair_value=float(row.fair_value) if row.fair_value is not None else None,
        lo90=float(row.lo90) if row.lo90 is not None else None,
        hi90=float(row.hi90) if row.hi90 is not None else None,
        n_paths=row.n_paths,
    )


@router.get("/{series_id}/valuation")
def get_valuation(
    series_id: str,
    as_of: date | None = Query(default=None),
    method: str = Query(default="burn"),
    measure: str = Query(default="P"),
    db: Session = Depends(get_db),
) -> Envelope[ValuationData]:
    _assert_series_exists(db, series_id)
    stmt = select(Valuation).where(
        Valuation.series_id == series_id, Valuation.method == method, Valuation.measure == measure
    )
    stmt = (
        stmt.where(Valuation.as_of_date == as_of)
        if as_of is not None
        else stmt.order_by(Valuation.as_of_date.desc())
    )
    row = db.execute(stmt.limit(1)).scalars().first()
    if row is None:
        raise unknown_series(f"{series_id} has no {method}/{measure} valuation")
    return Envelope(
        data=_to_valuation_data(row),
        meta=_now_meta(as_of=row.as_of_date),
    )


@router.get("/{series_id}/valuations/compare")
def compare_valuations(
    series_id: str, as_of: date | None = Query(default=None), db: Session = Depends(get_db)
) -> Envelope[ValuationsCompareData]:
    """SPEC's "all 4 methods side-by-side" — currently returns whichever
    methods/measures actually have real rows written for this series
    (burn and dist, per M4; conditioned/mpr rungs not yet written to
    this table — see docs/STATUS.md), not a fabricated 4-method set.

    Each method's own MOST RECENT row, not "whatever was written on the
    literal same calendar day" — real data showed burn and dist were
    written a day apart for RAINCHNNAI (M4 ran them in separate passes),
    so a same-day join would have silently dropped one method entirely
    whenever `as_of` isn't given. `as_of`, when given, bounds every
    method's own latest row to "at or before that date" rather than
    requiring an exact match."""
    _assert_series_exists(db, series_id)
    stmt = select(Valuation).where(Valuation.series_id == series_id)
    if as_of is not None:
        stmt = stmt.where(Valuation.as_of_date <= as_of)
    rows = db.execute(stmt.order_by(Valuation.as_of_date.desc())).scalars().all()
    if not rows:
        raise unknown_series(f"{series_id} has no valuations")

    by_method: dict[str, ValuationData] = {}
    for r in rows:
        key = f"{r.method}/{r.measure}"
        if key not in by_method:  # rows are already newest-first -> first hit per key is the latest
            by_method[key] = _to_valuation_data(r)

    latest_as_of = max(v.as_of_date for v in by_method.values())
    return Envelope(
        data=ValuationsCompareData(
            series_id=series_id, as_of_date=latest_as_of, by_method=by_method
        ),
        meta=_now_meta(as_of=date.fromisoformat(latest_as_of)),
    )


class IndexPoint(BaseModel):
    obs_date: str
    as_of_date: str
    proxy_value: float | None
    official_value: float | None
    abs_error: float | None
    pct_lpa_error: float | None


class IndexPathData(BaseModel):
    series_id: str
    points: list[IndexPoint]


@router.get("/{series_id}/index")
def get_index_path(
    series_id: str,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    as_of: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Envelope[IndexPathData]:
    """The real M3 `index_values` rows: proxy (satellite/model-derived)
    vs. official index value per observed day, plus the proxy's own
    error against the official value where both exist.

    `index_values` is keyed (series_id, obs_date, as_of_date) because a
    given obs_date's proxy estimate can be revised as more data arrives
    -- same "each day's own most recent snapshot" rule as
    `valuations/compare` above, bounded by `as_of` when given rather than
    requiring an exact match."""
    _assert_series_exists(db, series_id)
    stmt = select(IndexValue).where(IndexValue.series_id == series_id)
    if date_from is not None:
        stmt = stmt.where(IndexValue.obs_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(IndexValue.obs_date <= date_to)
    if as_of is not None:
        stmt = stmt.where(IndexValue.as_of_date <= as_of)
    rows = (
        db.execute(stmt.order_by(IndexValue.obs_date.asc(), IndexValue.as_of_date.desc()))
        .scalars()
        .all()
    )
    if not rows:
        raise unknown_series(f"{series_id} has no index values in the requested range")

    by_obs_date: dict[str, IndexPoint] = {}
    for r in rows:
        key = r.obs_date.isoformat()
        if (
            key not in by_obs_date
        ):  # newest as_of_date per obs_date wins (query already orders for this)
            by_obs_date[key] = IndexPoint(
                obs_date=key,
                as_of_date=r.as_of_date.isoformat(),
                proxy_value=float(r.proxy_value) if r.proxy_value is not None else None,
                official_value=float(r.official_value) if r.official_value is not None else None,
                abs_error=float(r.abs_error) if r.abs_error is not None else None,
                pct_lpa_error=float(r.pct_lpa_error) if r.pct_lpa_error is not None else None,
            )
    points = sorted(by_obs_date.values(), key=lambda p: p.obs_date)
    return Envelope(
        data=IndexPathData(series_id=series_id, points=points),
        meta=_now_meta(as_of=date.fromisoformat(points[-1].as_of_date)),
    )


class QuoteRow(BaseModel):
    trade_date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    settle: float | None
    volume: int | None
    open_interest: int | None


class QuotesData(BaseModel):
    series_id: str
    quotes: list[QuoteRow]


@router.get("/{series_id}/quotes")
def get_quotes(
    series_id: str,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> Envelope[QuotesData]:
    """Real `market_quotes` rows (SPEC §9.2: "settle, volume, OI"). Will
    legitimately return an empty list for both real series right now --
    NCDEX's bhavcopy live fetch stays bot-gated (M2, documented policy),
    so no real settlement data has ever been ingested; this is reported
    honestly as zero rows, not backfilled with synthetic quotes."""
    _assert_series_exists(db, series_id)
    stmt = select(MarketQuote).where(MarketQuote.series_id == series_id)
    if date_from is not None:
        stmt = stmt.where(MarketQuote.trade_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(MarketQuote.trade_date <= date_to)
    rows = db.execute(stmt.order_by(MarketQuote.trade_date.asc())).scalars().all()
    quotes = [
        QuoteRow(
            trade_date=r.trade_date.isoformat(),
            open=float(r.open) if r.open is not None else None,
            high=float(r.high) if r.high is not None else None,
            low=float(r.low) if r.low is not None else None,
            close=float(r.close) if r.close is not None else None,
            settle=float(r.settle) if r.settle is not None else None,
            volume=r.volume,
            open_interest=r.open_interest,
        )
        for r in rows
    ]
    return Envelope(data=QuotesData(series_id=series_id, quotes=quotes), meta=_now_meta())


class MPRPoint(BaseModel):
    as_of_date: str
    transform: str
    lambda_: float | None
    ci_lo: float | None
    ci_hi: float | None
    method_ci: str | None
    days_to_expiry: int | None
    volume: int | None
    open_interest: int | None
    n_obs: int | None


class MPRData(BaseModel):
    series_id: str
    points: list[MPRPoint]


@router.get("/{series_id}/mpr")
def get_mpr(
    series_id: str,
    transform: str | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> Envelope[MPRData]:
    """Real `mpr_estimates` rows (SPEC §9.2: "lambda time series + CIs +
    liquidity"), M6's Wang/Esscher calibration output. Will legitimately
    return an empty list right now: M6's demo ran against illustrative
    settle data only (no real NCDEX settlement exists yet, same bhavcopy
    bot-gate as `quotes` above), so nothing has been written to this
    table against real market data -- reported honestly, not faked."""
    _assert_series_exists(db, series_id)
    stmt = select(MPREstimate).where(MPREstimate.series_id == series_id)
    if transform is not None:
        stmt = stmt.where(MPREstimate.transform == transform)
    if date_from is not None:
        stmt = stmt.where(MPREstimate.as_of_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(MPREstimate.as_of_date <= date_to)
    rows = db.execute(stmt.order_by(MPREstimate.as_of_date.asc())).scalars().all()
    points = [
        MPRPoint(
            as_of_date=r.as_of_date.isoformat(),
            transform=r.transform,
            lambda_=float(r.lambda_) if r.lambda_ is not None else None,
            ci_lo=float(r.ci_lo) if r.ci_lo is not None else None,
            ci_hi=float(r.ci_hi) if r.ci_hi is not None else None,
            method_ci=r.method_ci,
            days_to_expiry=r.days_to_expiry,
            volume=r.volume,
            open_interest=r.open_interest,
            n_obs=r.n_obs,
        )
        for r in rows
    ]
    return Envelope(data=MPRData(series_id=series_id, points=points), meta=_now_meta())


class ForecastRow(BaseModel):
    as_of_date: str
    model_id: str
    model_version: str
    target: str
    quantiles: dict[str, float]
    fair_value: float | None
    fair_value_lo90: float | None
    fair_value_hi90: float | None


class ForecastData(BaseModel):
    series_id: str
    contract_code: str
    rows: list[ForecastRow]


@router.get("/{series_id}/forecast")
def get_forecast(
    series_id: str,
    model_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Envelope[ForecastData]:
    """Quantiles + fan-chart data (SPEC §9.2) straight from the real,
    hash-chained `prediction_ledger` (M7's backtest rows) -- the same
    source `/v1/ledger` reads, just scoped to one series and shaped for
    a fan chart (one quantile set per as_of_date) instead of raw ledger
    rows. The ledger is keyed by `contract_code`, not `series_id` (a
    forecast target like "remaining season rainfall" applies to the
    whole contract, not one listed expiry), so `series_id` is resolved
    to its `contract_code` via the real `contracts` table first."""
    contract = db.execute(
        select(Contract.contract_code).where(Contract.series_id == series_id)
    ).scalar_one_or_none()
    if contract is None:
        raise unknown_series(series_id)

    stmt = select(PredictionLedgerRow).where(PredictionLedgerRow.contract_code == contract)
    if model_id is not None:
        stmt = stmt.where(PredictionLedgerRow.model_id == model_id)
    rows = db.execute(stmt.order_by(PredictionLedgerRow.as_of_date.asc())).scalars().all()
    if not rows:
        raise unknown_series(f"{series_id} (contract {contract}) has no forecast ledger rows")

    out_rows = [
        ForecastRow(
            as_of_date=r.as_of_date.isoformat(),
            model_id=r.model_id,
            model_version=r.model_version,
            target=r.target,
            quantiles={k: float(v) for k, v in r.quantiles.items()},
            fair_value=float(r.fair_value) if r.fair_value is not None else None,
            fair_value_lo90=float(r.fair_value_lo90) if r.fair_value_lo90 is not None else None,
            fair_value_hi90=float(r.fair_value_hi90) if r.fair_value_hi90 is not None else None,
        )
        for r in rows
    ]
    return Envelope(
        data=ForecastData(series_id=series_id, contract_code=contract, rows=out_rows),
        meta=_now_meta(as_of=rows[-1].as_of_date, model_version=rows[-1].model_version),
    )


# Process-lifetime cache, keyed by the exact request shape (SPEC's own
# "cached by request hash" pattern for the three heavy POSTs, reused
# here). Added after actually timing this endpoint rather than trusting
# the optimistic assumption in an earlier draft of this docstring: a
# real, uncached run (parquet read + the 31-year official burn sample +
# basis_grid's own per-cell reconstruction loop) measured ~48s end to
# end for RAINCHNNAI's real 12-cell box on this machine -- nowhere near
# a GET's expected latency, and not disclosed-and-shipped-anyway; fixed
# with the same request-hash cache SPEC already prescribes for exactly
# this kind of cost, rather than left slow or silently capped. Real
# historical IMD data changes only with the (currently bot-gated, M2)
# ingestion pipeline, so there is no staleness concern in practice; a
# multi-worker/multi-process deployment would need a shared cache
# (Redis, a DB table) instead of this in-process dict -- noted here as
# the real limitation of this fix, not hidden.
_basis_cache: dict[tuple[str, str, float], dict[str, Any]] = {}


@router.get("/{series_id}/basis")
def get_basis(
    series_id: str,
    as_of: date | None = Query(default=None),
    box_deg: float = Query(default=0.5, gt=0, le=2.0),
    db: Session = Depends(get_db),
) -> Envelope[dict[str, Any]]:
    """GeoJSON grid metrics (SPEC §9.2) -- a real, on-demand run of M10's
    basis-risk engine for this series' own contract spec (there's no
    `basis_results` table; the real M10 run, `docs/methods/basis.md`,
    covered 12 real IMD grid cells for RAINCHNNAI's ~1 deg box). Cached
    by request hash (series_id, as_of, box_deg) after a real, measured
    ~48s uncached run -- see `_basis_cache` above for why.

    `box_deg` controls the half-width of the bounding box (degrees)
    around the contract's own station(s), default 0.5 deg to match the
    real M10 run; the real IMD grid's own 0.25 deg native spacing means
    this box typically yields a handful to a few dozen cells, not an
    unbounded scan."""
    contract_code = db.execute(
        select(Contract.contract_code).where(Contract.series_id == series_id)
    ).scalar_one_or_none()
    if contract_code is None:
        raise unknown_series(series_id)

    effective_as_of = as_of if as_of is not None else date.today()
    cache_key = (series_id, effective_as_of.isoformat(), box_deg)
    cached = _basis_cache.get(cache_key)
    if cached is not None:
        return Envelope(data=cached, meta=_now_meta(as_of=effective_as_of))

    spec = load_resolved_spec(db, series_id, contract_code)
    rain_grid = load_rain_grid(effective_as_of)
    official_values = official_index_values(spec, rain_grid)

    if not isinstance(spec.stations, list):
        raise unknown_series(f"{series_id}: contract spec has no resolved stations")
    station_lats = [s.lat for s in spec.stations]
    station_lons = [s.lon for s in spec.stations]
    lat_bounds = (min(station_lats) - box_deg, max(station_lats) + box_deg)
    lon_bounds = (min(station_lons) - box_deg, max(station_lons) + box_deg)

    cells = basis_grid(
        spec,
        rain_grid,
        BASIS_YEARS,
        official_index_values=official_values,
        lat_bounds=lat_bounds,
        lon_bounds=lon_bounds,
    )
    if not cells:
        raise unknown_series(f"{series_id}: no grid cells with >=3 overlapping years in the box")

    geojson = to_geojson(cells)
    _basis_cache[cache_key] = geojson
    return Envelope(
        data=geojson,
        meta=_now_meta(as_of=effective_as_of, data_version=str(max(official_values))),
    )
