"""Hedge optimiser, min-variance half (SPEC §7.9).

    h* = -Cov(L, X) / Var(X)      position: L + h*X
    hedge effectiveness = 1 - Var(L + h*X) / Var(L)

**Sign convention, stated explicitly because it differs from
`mq.risk.basis`'s own `hedge_ratio`**: SPEC's formula here is written
for the position `L + h*X` (hedge units of the index *added* to the
exposure) — a negative `h` means going short the contract. `mq.risk.basis`
instead reports a basis-risk *diagnostic* for `L - h*X` (the standard
regression-hedge-ratio framing), which is the same minimum-variance
decomposition but with the opposite sign: `mq.risk.basis`'s
`hedge_ratio` equals `-1 *` this module's `h_star` for the same
`(L, X)` pair. Both are correct for what they each report; only this
module's sign is meant to be read as an actionable "go long/short"
instruction.

**Exposure templates** (SPEC's four named ones, plus the "custom
piecewise-linear" building block they're all expressed through): a
single `PiecewiseLinearExposure` — breakpoints and slopes — covers all
five, since every named template (delivery-rider income loss, crop
yield loss, event cancellation, construction downtime) is itself a
piecewise-linear function of local rainfall, just with a different
shape/sign. These are **illustrative templates**, not calibrated to any
specific real business — SPEC's own §7.11 case study (synthetic
delivery-rider exposure) is explicitly labelled synthetic, and these
templates inherit that same posture.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class PiecewiseLinearExposure:
    """L = g(rain_mm): piecewise-linear in rain, defined by breakpoints
    (rain_mm, loss_at_that_point) sorted ascending, with the first and
    last segments extended as flat (clamped) beyond the outer
    breakpoints — a bounded loss model, not one that explodes for an
    extreme rain value outside the fitted range."""

    breakpoints_rain_mm: list[float]
    breakpoints_loss: list[float]

    def __post_init__(self) -> None:
        if len(self.breakpoints_rain_mm) != len(self.breakpoints_loss):
            raise ValueError("breakpoints_rain_mm and breakpoints_loss must be the same length")
        if len(self.breakpoints_rain_mm) < 2:
            raise ValueError("need at least 2 breakpoints to define a piecewise-linear exposure")
        if list(self.breakpoints_rain_mm) != sorted(self.breakpoints_rain_mm):
            raise ValueError("breakpoints_rain_mm must be sorted ascending")

    def __call__(self, rain_mm: np.ndarray) -> np.ndarray:
        return np.asarray(np.interp(rain_mm, self.breakpoints_rain_mm, self.breakpoints_loss))


def delivery_rider_income_loss(
    *, dry_threshold_mm: float = 50.0, saturation_mm: float = 200.0, max_loss: float = 1000.0
) -> PiecewiseLinearExposure:
    """Income loss starts at `dry_threshold_mm` (deliveries slow once
    rain picks up) and saturates at `max_loss` once rain is heavy enough
    that deliveries stop almost entirely."""
    return PiecewiseLinearExposure(
        breakpoints_rain_mm=[0.0, dry_threshold_mm, saturation_mm],
        breakpoints_loss=[0.0, 0.0, max_loss],
    )


def crop_yield_loss(
    *,
    drought_threshold_mm: float = 300.0,
    total_failure_mm: float = 100.0,
    max_loss: float = 1000.0,
) -> PiecewiseLinearExposure:
    """Mirror-direction exposure: loss INCREASES as rain falls below
    `drought_threshold_mm`, reaching `max_loss` at `total_failure_mm`
    (a dry-season failure point) — the opposite shape from the wet-side
    templates above."""
    return PiecewiseLinearExposure(
        breakpoints_rain_mm=[0.0, total_failure_mm, drought_threshold_mm],
        breakpoints_loss=[max_loss, max_loss, 0.0],
    )


def event_cancellation_loss(
    *, trigger_mm: float = 20.0, loss: float = 1000.0
) -> PiecewiseLinearExposure:
    """Approximately a step function (an outdoor event is either ruined
    or not) — modelled as a steep but still piecewise-linear ramp over a
    narrow band around `trigger_mm`, rather than a true discontinuity,
    so it stays compatible with everything else in this module that
    assumes a continuous `g`."""
    ramp_width = max(1.0, trigger_mm * 0.05)
    return PiecewiseLinearExposure(
        breakpoints_rain_mm=[0.0, trigger_mm - ramp_width / 2, trigger_mm + ramp_width / 2],
        breakpoints_loss=[0.0, 0.0, loss],
    )


def construction_downtime_loss(
    *, rain_day_threshold_mm: float = 10.0, saturation_mm: float = 150.0, max_loss: float = 1000.0
) -> PiecewiseLinearExposure:
    """Same wet-side shape as `delivery_rider_income_loss` with
    different default breakpoints (construction sites typically tolerate
    less rain before work stops than delivery logistics do)."""
    return PiecewiseLinearExposure(
        breakpoints_rain_mm=[0.0, rain_day_threshold_mm, saturation_mm],
        breakpoints_loss=[0.0, 0.0, max_loss],
    )


@dataclass(frozen=True)
class LotConstraints:
    max_order_lots: int | None = None
    position_limit_lots: int | None = None
    margin_budget: float | None = None
    margin_per_lot: float | None = None
    max_notional: float | None = None
    notional_per_lot: float | None = None
    long_allowed: bool = True
    short_allowed: bool = True

    def lot_bounds(self) -> tuple[int, int]:
        """(min_lots, max_lots), min possibly negative (short)."""
        upper_candidates = [
            c for c in [self.max_order_lots, self.position_limit_lots] if c is not None
        ]
        if self.margin_budget is not None and self.margin_per_lot:
            upper_candidates.append(int(self.margin_budget // self.margin_per_lot))
        if self.max_notional is not None and self.notional_per_lot:
            upper_candidates.append(int(self.max_notional // self.notional_per_lot))
        max_lots = min(upper_candidates) if upper_candidates else 10_000
        min_lots = -max_lots
        if not self.long_allowed:
            max_lots = 0
        if not self.short_allowed:
            min_lots = 0
        return min_lots, max_lots


@dataclass(frozen=True)
class HedgeReport:
    h_star: float  # continuous optimal hedge units of index per unit exposure
    lots: int  # integer lots after rounding + clamping to constraints
    h_realized: float  # lots * multiplier -- what the integer position actually achieves
    hedge_effectiveness: float  # 1 - Var(L + h_realized*X) / Var(L)
    residual_variance: float
    do_nothing_variance: float  # Var(L): the "do-nothing" comparison SPEC asks for
    # fraction of residual variance attributable to basis risk vs MV rounding error
    basis_contribution: float
    constraints: LotConstraints = field(default_factory=LotConstraints)


def min_variance_hedge(
    exposure: np.ndarray,
    index: np.ndarray,
    *,
    multiplier: float,
    constraints: LotConstraints | None = None,
) -> HedgeReport:
    """`exposure` (L) and `index` (X) are paired scenario arrays (e.g.
    M10's `mq.risk.basis.local_index_series`'s values run through an
    exposure template, and the real official index series)."""
    if len(exposure) != len(index):
        raise ValueError("exposure and index must have the same length")
    if len(exposure) < 2:
        raise ValueError("need at least 2 scenarios")
    constraints = constraints or LotConstraints()

    var_index = float(np.var(index, ddof=1))
    var_exposure = float(np.var(exposure, ddof=1))
    h_star = 0.0 if var_index == 0 else -float(np.cov(exposure, index, ddof=1)[0, 1]) / var_index

    min_lots, max_lots = constraints.lot_bounds()
    lots_continuous = h_star / multiplier if multiplier != 0 else 0.0
    lots = int(np.clip(round(lots_continuous), min_lots, max_lots))
    h_realized = lots * multiplier

    hedged = exposure + h_realized * index
    residual_variance = float(np.var(hedged, ddof=1))
    hedge_effectiveness = 0.0 if var_exposure == 0 else 1.0 - residual_variance / var_exposure

    # basis_contribution: of whatever variance remains after hedging,
    # how much is "structural" basis risk (residual variance at the
    # CONTINUOUS, unconstrained optimum -- the best any integer-lot
    # position could ever do) versus the extra slack introduced by
    # rounding/clamping to a feasible integer lot count.
    hedged_at_h_star = exposure + h_star * index
    residual_at_h_star = float(np.var(hedged_at_h_star, ddof=1))
    basis_contribution = (
        1.0 if residual_variance == 0 else min(1.0, residual_at_h_star / residual_variance)
    )

    return HedgeReport(
        h_star=h_star,
        lots=lots,
        h_realized=h_realized,
        hedge_effectiveness=hedge_effectiveness,
        residual_variance=residual_variance,
        do_nothing_variance=var_exposure,
        basis_contribution=basis_contribution,
        constraints=constraints,
    )
