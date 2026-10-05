"""Parametric cover designer (SPEC §7.11).

    payout = min(limit, slope * max(0, I - trigger))   (wet cover: pays on excess rain)
    payout = min(limit, slope * max(0, trigger - I))   (dry cover: pays on drought)
    premium = E_Q[payout] * (1 + loading), discounted

Optimises `(trigger, slope, limit)` to minimize the "basis-failure
probability" `P(loss > threshold AND payout == 0)` — paying a premium
for a cover that still pays nothing in exactly the seasons the buyer
needed it — subject to `premium <= budget`. Grid search (over the
budget-respecting region) + Nelder-Mead refinement, SPEC's own stated
method.

**Deliberately built on what M4/M6/M9/M10 already provide**: the
Q-measure expectation reuses `mq.mpr.wang.wang_price` directly (a
payout is just another sample array to reweight — the Wang transform
doesn't care that it's a capped/floored function of the index rather
than the raw index); the loss model reuses `mq.risk.hedge`'s
`PiecewiseLinearExposure` templates; the joint (loss, index) scenarios
are the same shape `mq.risk.basis.local_index_series` already produces.

**Case study** (SPEC's own stated one): a synthetic Chennai
delivery-rider income exposure, labelled synthetic per SPEC's own
instruction — reuses `mq.risk.hedge.delivery_rider_income_loss`
directly, same posture as M9's hedge-optimiser demo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from mq.mpr.wang import wang_price


@dataclass(frozen=True)
class ParametricCoverParams:
    trigger: float
    slope: float
    limit: float
    direction: str  # "wet" or "dry"

    def __post_init__(self) -> None:
        if self.direction not in ("wet", "dry"):
            raise ValueError(f"direction must be 'wet' or 'dry', got {self.direction!r}")


def wet_cover_payout(
    index: np.ndarray, *, trigger: float, slope: float, limit: float
) -> np.ndarray:
    return np.minimum(limit, slope * np.maximum(0.0, index - trigger))


def dry_cover_payout(
    index: np.ndarray, *, trigger: float, slope: float, limit: float
) -> np.ndarray:
    return np.minimum(limit, slope * np.maximum(0.0, trigger - index))


def payout_for(index: np.ndarray, params: ParametricCoverParams) -> np.ndarray:
    fn = wet_cover_payout if params.direction == "wet" else dry_cover_payout
    return fn(index, trigger=params.trigger, slope=params.slope, limit=params.limit)


def premium(
    index: np.ndarray,
    params: ParametricCoverParams,
    *,
    lam: float,
    loading: float,
    discount_factor: float = 1.0,
) -> float:
    """`lam` is the Wang-transform risk parameter (`mq.mpr.wang`) —
    pass `lam=0.0` for a pure physical-measure expected payout (no risk
    loading beyond the explicit `loading` multiplier)."""
    payout = payout_for(index, params)
    expected_q = wang_price(payout, lam)
    return float(expected_q * (1.0 + loading) * discount_factor)


def basis_failure_probability(
    loss: np.ndarray, payout: np.ndarray, *, loss_threshold: float
) -> float:
    """P(loss exceeded the threshold AND the cover paid nothing) — the
    scenario a buyer fears most: they paid a premium, suffered a real
    loss, and the parametric trigger still didn't fire."""
    if len(loss) != len(payout):
        raise ValueError("loss and payout must have the same length")
    return float(np.mean((loss > loss_threshold) & (payout == 0.0)))


@dataclass(frozen=True)
class OptimizedCover:
    params: ParametricCoverParams
    premium: float
    basis_failure_probability: float
    converged: bool
    n_grid_evaluated: int


def optimize_cover(
    loss: np.ndarray,
    index: np.ndarray,
    *,
    direction: str,
    loss_threshold: float,
    budget: float,
    lam: float = 0.0,
    loading: float = 0.0,
    trigger_grid: Sequence[float],
    slope_grid: Sequence[float],
    limit_grid: Sequence[float],
) -> OptimizedCover:
    """Grid search over `(trigger_grid, slope_grid, limit_grid)`
    restricted to combinations whose premium is within `budget`, then a
    Nelder-Mead refinement starting from the grid optimum — SPEC's own
    stated "grid search + Nelder-Mead refine"."""
    if len(loss) != len(index):
        raise ValueError("loss and index must have the same length")

    best: tuple[float, ParametricCoverParams, float] | None = None
    n_evaluated = 0
    for trigger in trigger_grid:
        for slope in slope_grid:
            for limit in limit_grid:
                n_evaluated += 1
                params = ParametricCoverParams(
                    trigger=trigger, slope=slope, limit=limit, direction=direction
                )
                prem = premium(index, params, lam=lam, loading=loading)
                if prem > budget:
                    continue
                payout = payout_for(index, params)
                bfp = basis_failure_probability(loss, payout, loss_threshold=loss_threshold)
                if best is None or bfp < best[0]:
                    best = (bfp, params, prem)

    if best is None:
        raise ValueError(
            "no (trigger, slope, limit) combination on the grid respects the premium budget "
            f"(budget={budget}) -- widen the grids or raise the budget"
        )
    grid_bfp, grid_params, grid_premium = best

    def objective(x: np.ndarray) -> float:
        trigger, slope, limit = x
        if limit <= 0 or slope <= 0:
            return 1e6  # keep the search away from a degenerate zero/negative cover
        candidate = ParametricCoverParams(
            trigger=float(trigger), slope=float(slope), limit=float(limit), direction=direction
        )
        prem = premium(index, candidate, lam=lam, loading=loading)
        payout = payout_for(index, candidate)
        bfp = basis_failure_probability(loss, payout, loss_threshold=loss_threshold)
        over_budget_penalty = 0.0 if prem <= budget else (prem - budget) * 10.0
        return bfp + over_budget_penalty

    result = minimize(
        objective,
        x0=np.array([grid_params.trigger, grid_params.slope, grid_params.limit]),
        method="Nelder-Mead",
    )
    trigger, slope, limit = result.x
    refined_params = ParametricCoverParams(
        trigger=float(trigger),
        slope=max(1e-9, float(slope)),
        limit=max(0.0, float(limit)),
        direction=direction,
    )
    refined_premium = premium(index, refined_params, lam=lam, loading=loading)

    if refined_premium > budget:
        # Nelder-Mead's unconstrained wandering violated the budget --
        # fall back to the grid optimum, which is guaranteed feasible.
        return OptimizedCover(
            params=grid_params,
            premium=grid_premium,
            basis_failure_probability=grid_bfp,
            converged=False,
            n_grid_evaluated=n_evaluated,
        )

    refined_payout = payout_for(index, refined_params)
    refined_bfp = basis_failure_probability(loss, refined_payout, loss_threshold=loss_threshold)
    return OptimizedCover(
        params=refined_params,
        premium=refined_premium,
        basis_failure_probability=refined_bfp,
        converged=bool(result.success),
        n_grid_evaluated=n_evaluated,
    )
