"""Chain-dependent rainfall model fitting (SPEC §7.4, F10, M5.1).

Fits the two building blocks of the Richardson-type stochastic simulator:

- **Occurrence**: a 1st-order 2-state Markov chain (`p01(d)` = P(wet
  tomorrow | dry today), `p11(d)` = P(wet tomorrow | wet today)), each a
  logistic GLM on Fourier harmonics of day-of-year plus climate-driver
  covariates (ONI, DMI — MJO omitted, still bot-gate-blocked per
  docs/DECISIONS.md).
- **Amount | wet**: a Gamma GLM (log link) on the same features.

No statsmodels/sklearn dependency: both GLMs are plain MLE fits via
`scipy.optimize`, the same hand-rolled-with-scipy style already used in
`mq.pricing.distribution` — these are small (~10-parameter) fits over
thousands of rows, well within what `scipy.optimize.minimize` handles
directly, and it avoids a new ~50MB+ dependency for something this
project can fit itself.

Feeds the NumPy reference simulator (M5.2, `simulator_ref.py`) and later
the C++ core (M5.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl
from scipy import optimize, special

from mq.io.grid import nearest_cell

WET_THRESHOLD_MM = 0.1
"""A day counts as "wet" at or above this. This is the Richardson-type
chain-dependent-model convention (react to any measurable rain; the
Gamma amount model carries the magnitude) — not IMD's own 2.5mm "rainy
day" threshold used for agromet reporting. Not a VERIFY item (no
contract term depends on it): a methodology choice, so it's documented
here rather than silently assumed."""

FOURIER_PERIOD_DAYS = 365.25
"""Continuous annual period for the Fourier harmonics — using 365.25
rather than 365 avoids a Dec 31/Jan 1 phase discontinuity in leap years
without needing lpa.py's Feb-29-exclusion trick (that trick suits a
calendar-day lookup table; a continuous periodic regressor doesn't need
it)."""


def fourier_design(day_of_year: np.ndarray, *, n_harmonics: int) -> np.ndarray:
    """Design-matrix columns: [1, sin(2*pi*k*doy/P), cos(2*pi*k*doy/P) for
    k in 1..n_harmonics], P = FOURIER_PERIOD_DAYS. Column 0 is the
    intercept."""
    doy = np.asarray(day_of_year, dtype=float)
    cols = [np.ones_like(doy)]
    for k in range(1, n_harmonics + 1):
        angle = 2 * np.pi * k * doy / FOURIER_PERIOD_DAYS
        cols.append(np.sin(angle))
        cols.append(np.cos(angle))
    return np.stack(cols, axis=1)


@dataclass(frozen=True)
class GLMFit:
    kind: str  # "logistic" | "gamma_log"
    coef: np.ndarray  # design-matrix column order: [intercept, fourier..., covariates...]
    n_obs: int
    converged: bool
    extra: dict[str, float] = field(default_factory=dict)  # e.g. {"shape": ...} for gamma_log


def fit_logistic(X: np.ndarray, y: np.ndarray) -> GLMFit:
    """MLE logistic regression (y in {0,1}) via BFGS on the binomial
    negative log-likelihood, with its analytic gradient supplied — plain
    MLE, no regularization (the +50MB sklearn dependency it would spare
    isn't needed at this feature count)."""
    n, p = X.shape

    def neg_log_lik(beta: np.ndarray) -> float:
        eta = X @ beta
        return float(np.sum(np.logaddexp(0.0, eta) - y * eta))

    def grad(beta: np.ndarray) -> np.ndarray:
        eta = X @ beta
        return -(X.T @ (y - special.expit(eta)))  # type: ignore[no-any-return]

    res = optimize.minimize(neg_log_lik, np.zeros(p), jac=grad, method="BFGS")
    return GLMFit(kind="logistic", coef=res.x, n_obs=n, converged=bool(res.success))


def predict_logistic(fit: GLMFit, X: np.ndarray) -> np.ndarray:
    return special.expit(X @ fit.coef)  # type: ignore[no-any-return]


def fit_gamma_log_link(X: np.ndarray, y: np.ndarray) -> GLMFit:
    """Gamma GLM, log link on the mean: mu = exp(X @ beta). The mean
    coefficients are fit by MLE (equivalent to IRLS at convergence,
    since the shape-only normalizing terms of the Gamma log-density
    don't depend on beta and can be dropped from the objective); the
    shape (1/dispersion) is then estimated from the Pearson residuals —
    the standard two-step Gamma-GLM dispersion estimate used by
    statsmodels/R's glm() (dispersion is a function of the fitted mean
    structure, not a second free MLE parameter in the usual
    quasi-likelihood formulation)."""
    n, p = X.shape

    def neg_log_lik(beta: np.ndarray) -> float:
        eta = X @ beta
        mu = np.exp(eta)
        return float(np.sum(y / mu + eta))

    def grad(beta: np.ndarray) -> np.ndarray:
        eta = X @ beta
        mu = np.exp(eta)
        return X.T @ (1.0 - y / mu)  # type: ignore[no-any-return]

    beta0 = np.zeros(p)
    beta0[0] = np.log(np.mean(y))
    res = optimize.minimize(neg_log_lik, beta0, jac=grad, method="BFGS")

    mu_hat = np.exp(X @ res.x)
    pearson_resid = (y - mu_hat) / mu_hat
    dispersion = float(np.sum(pearson_resid**2) / (n - p))
    shape = 1.0 / dispersion
    return GLMFit(
        kind="gamma_log",
        coef=res.x,
        n_obs=n,
        converged=bool(res.success),
        extra={"shape": shape, "dispersion": dispersion},
    )


def predict_gamma_mean(fit: GLMFit, X: np.ndarray) -> np.ndarray:
    return np.exp(X @ fit.coef)  # type: ignore[no-any-return]


def station_full_series(rain_grid: pl.DataFrame, *, lat: float, lon: float) -> pl.DataFrame:
    """This station's full multi-year daily series at its nearest grid
    cell — columns (date, rain_mm), sorted by date. `rain_grid` may span
    disjoint years (real backfill gaps, e.g. 2021-2022 missing) — callers
    building transition datasets must detect those gaps themselves via
    the date column, not assume contiguity."""
    cell_lat, cell_lon = nearest_cell(rain_grid, lat=lat, lon=lon)
    return (
        rain_grid.filter((pl.col("lat") == cell_lat) & (pl.col("lon") == cell_lon))
        .select("date", "rain_mm")
        .sort("date")
    )


def attach_monthly_covariate(
    daily: pl.DataFrame, climate_idx: pl.DataFrame, *, index_name: str, col_name: str
) -> pl.DataFrame:
    """Joins one monthly climate-driver series (long-format `climate_idx`,
    schema index/date/value/release_date — see `mq.pipelines.climate_idx`)
    onto `daily` by (year, month), as a new `col_name` column. Rows whose
    month has no matching observation are dropped (left join + drop-null,
    rather than guessing a value for a covariate gap)."""
    monthly = (
        climate_idx.filter(pl.col("index") == index_name)
        .with_columns(
            pl.col("date").dt.year().alias("_year"), pl.col("date").dt.month().alias("_month")
        )
        .select("_year", "_month", pl.col("value").alias(col_name))
    )
    joined = daily.with_columns(
        pl.col("date").dt.year().alias("_year"), pl.col("date").dt.month().alias("_month")
    ).join(monthly, on=["_year", "_month"], how="left")
    return joined.drop_nulls(col_name).drop("_year", "_month")


@dataclass(frozen=True)
class OccurrenceDataset:
    X01: np.ndarray  # rows where yesterday was dry
    y01: np.ndarray  # 1 if today is wet
    X11: np.ndarray  # rows where yesterday was wet
    y11: np.ndarray  # 1 if today is wet


def _valid_transition_mask(dates: pl.Series) -> np.ndarray:
    """True at index i (i>=1) iff dates[i] is exactly one day after
    dates[i-1] — the only transitions a 1st-order Markov chain can
    legitimately use. A real backfill gap (or a year-file boundary with
    missing years in between) must not be silently treated as a
    same-day-apart transition."""
    diffs = dates.diff().dt.total_days().to_numpy()
    return diffs[1:] == 1  # type: ignore[no-any-return]  # diffs[0] is null (no previous row)


def build_occurrence_dataset(
    daily: pl.DataFrame, *, n_harmonics: int, covariate_cols: list[str]
) -> OccurrenceDataset:
    """`daily` must have columns (date, rain_mm, *covariate_cols), sorted
    by date, and may span gaps — see `_valid_transition_mask`."""
    d = daily.sort("date")
    wet = (d["rain_mm"] >= WET_THRESHOLD_MM).to_numpy().astype(float)
    doy = d["date"].dt.ordinal_day().to_numpy().astype(float)
    cov = (
        np.column_stack([d[c].to_numpy() for c in covariate_cols])
        if covariate_cols
        else np.zeros((d.height, 0))
    )
    X_full = np.concatenate([fourier_design(doy, n_harmonics=n_harmonics), cov], axis=1)

    valid = _valid_transition_mask(d["date"])
    prev_wet = wet[:-1][valid]
    curr_wet = wet[1:][valid]
    X_t = X_full[1:][valid]  # features of the day being predicted

    dry_mask = prev_wet == 0.0
    wet_mask = prev_wet == 1.0
    return OccurrenceDataset(
        X01=X_t[dry_mask], y01=curr_wet[dry_mask], X11=X_t[wet_mask], y11=curr_wet[wet_mask]
    )


def build_amount_dataset(
    daily: pl.DataFrame, *, n_harmonics: int, covariate_cols: list[str]
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (X, amounts) over wet days only — the Gamma-GLM training
    set. No transition structure here (unlike occurrence), so no gap
    handling is needed: each wet day's amount is independent of its
    neighbours in this model."""
    d = daily.sort("date")
    wet_mask = (d["rain_mm"] >= WET_THRESHOLD_MM).to_numpy()
    doy = d["date"].dt.ordinal_day().to_numpy().astype(float)
    cov = (
        np.column_stack([d[c].to_numpy() for c in covariate_cols])
        if covariate_cols
        else np.zeros((d.height, 0))
    )
    X_full = np.concatenate([fourier_design(doy, n_harmonics=n_harmonics), cov], axis=1)
    return X_full[wet_mask], d["rain_mm"].to_numpy()[wet_mask]


@dataclass(frozen=True)
class ChainModel:
    """Everything needed to simulate/evaluate the chain-dependent model
    for one station: the two occurrence GLMs (p01, p11) and the wet-day
    amount GLM, all sharing the same Fourier-harmonic order and
    covariate columns so a caller can build one feature vector per day
    and reuse it for all three."""

    n_harmonics: int
    covariate_cols: list[str]
    occurrence_01: GLMFit
    occurrence_11: GLMFit
    amount: GLMFit


def fit_chain_model(
    daily_with_covariates: pl.DataFrame, *, n_harmonics: int, covariate_cols: list[str]
) -> ChainModel:
    occ = build_occurrence_dataset(
        daily_with_covariates, n_harmonics=n_harmonics, covariate_cols=covariate_cols
    )
    X_amt, y_amt = build_amount_dataset(
        daily_with_covariates, n_harmonics=n_harmonics, covariate_cols=covariate_cols
    )
    return ChainModel(
        n_harmonics=n_harmonics,
        covariate_cols=covariate_cols,
        occurrence_01=fit_logistic(occ.X01, occ.y01),
        occurrence_11=fit_logistic(occ.X11, occ.y11),
        amount=fit_gamma_log_link(X_amt, y_amt),
    )
