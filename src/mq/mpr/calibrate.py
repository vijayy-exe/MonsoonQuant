"""Calibrates each transform's single risk parameter (λ for Wang, θ for
Esscher) to match an observed settlement price: solve price_Q(param) =
settle via Brent's method, param bounded in [-3, 3] (SPEC §7.5) — the
same bound serves both transforms because Esscher is defined on the
standardized payoff (see esscher.py's docstring), putting both
parameters on a comparable O(1) scale.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy import optimize

from mq.mpr.esscher import LowEffectiveSampleSizeError, esscher_price
from mq.mpr.wang import wang_price

DEFAULT_BOUNDS = (-3.0, 3.0)


@dataclass(frozen=True)
class CalibrationResult:
    param: float
    converged: bool
    price_at_param: float
    settle: float
    note: str = ""


def _bracketed_solve(
    gap: Callable[[float], float],
    bounds: tuple[float, float],
) -> CalibrationResult:
    lo, hi = bounds
    glo, ghi = gap(lo), gap(hi)
    if (glo > 0) == (ghi > 0):
        # settle lies outside what's achievable within these bounds —
        # a corner solution, not a crash: report whichever bound comes
        # closer, flagged as not converged, so the caller sees the
        # mismatch rather than a silently wrong in-bracket number.
        param = lo if abs(glo) < abs(ghi) else hi
        return CalibrationResult(
            param=param,
            converged=False,
            price_at_param=np.nan,  # filled in by the caller, which knows which price_fn to use
            settle=np.nan,
            note=f"settle unreachable within bounds={bounds} — reporting nearest corner",
        )
    param = optimize.brentq(gap, lo, hi, xtol=1e-4)
    return CalibrationResult(param=param, converged=True, price_at_param=np.nan, settle=np.nan)


def calibrate_wang(
    payoffs: np.ndarray, settle: float, *, bounds: tuple[float, float] = DEFAULT_BOUNDS
) -> CalibrationResult:
    def gap(lam: float) -> float:
        return wang_price(payoffs, lam) - settle

    result = _bracketed_solve(gap, bounds)
    price = wang_price(payoffs, result.param)
    return CalibrationResult(
        param=result.param,
        converged=result.converged,
        price_at_param=price,
        settle=settle,
        note=result.note,
    )


def calibrate_esscher(
    payoffs: np.ndarray,
    settle: float,
    *,
    bounds: tuple[float, float] = DEFAULT_BOUNDS,
    min_ess_fraction: float = 0.01,
) -> CalibrationResult:
    """Like `calibrate_wang`, but a candidate θ near either bound may
    make `esscher_price` refuse outright (ESS too low) rather than
    return a number — treated as "this bound is unreachable", same as
    an ordinary sign mismatch, not as an unhandled crash."""

    def gap(theta: float) -> float:
        try:
            return esscher_price(payoffs, theta, min_ess_fraction=min_ess_fraction) - settle
        except LowEffectiveSampleSizeError:
            # Push the bisection away from this theta: a large
            # same-signed residual at an unusable theta still lets
            # brentq treat it as "far from the root", without ever
            # feeding the root-finder a NaN.
            return np.sign(theta) * 1e6 if theta != 0 else 1e6

    result = _bracketed_solve(gap, bounds)
    try:
        price = esscher_price(payoffs, result.param, min_ess_fraction=min_ess_fraction)
        note = result.note
    except LowEffectiveSampleSizeError as exc:
        price = np.nan
        note = f"{result.note} (ESS refused at reported param: {exc})".strip()
    return CalibrationResult(
        param=result.param,
        converged=result.converged,
        price_at_param=price,
        settle=settle,
        note=note,
    )
