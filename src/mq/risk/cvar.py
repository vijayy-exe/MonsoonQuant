"""CVaR95 hedge optimisation, CVaR half of SPEC §7.9's hedge optimiser.

Solved via `scipy.optimize.linprog`'s HiGHS backend — the literal
solver SPEC names ("Rockafellar-Uryasev LP via cvxpy/HiGHS"), already
available through the existing scipy dependency (its default `method`
in this scipy version), so no new dependency (cvxpy) is added for this.

The Rockafellar-Uryasev formulation minimizes CVaR_alpha of the hedged
loss `L + h*X` over the hedge ratio `h`, jointly with the auxiliary
VaR/shortfall variables it introduces:

    minimize_{h, zeta, u}  zeta + 1/((1-alpha)*N) * sum(u_i)
    s.t.                   u_i >= (L_i + h*X_i) - zeta   for each scenario i
                            u_i >= 0
                            h_min <= h <= h_max

At the optimum, `zeta` is the VaR_alpha of the hedged loss and the
objective value is its CVaR_alpha — this is what makes the problem
linear despite CVaR itself being defined via a quantile.

**Integer lots**: SPEC allows "enumeration over feasible lots (cap
small)" as an alternative to a full MILP. Solving the continuous LP
once, then evaluating the *exact* empirical CVaR directly on the
scenarios for a small neighborhood of candidate integer lot counts
around that continuous optimum, is cheap at this scale and avoids
needing a MILP solver (another dependency) for what SPEC itself treats
as an acceptable shortcut.

**Why `constraints` (bounding `h`) is load-bearing here, not just a
risk-management nicety**: unlike variance, which is quadratic in `h`
and always has a unique interior minimum, CVaR minimization can be
genuinely *unbounded* when the index's sign doesn't vary across the
scenario set. If `X_i > 0` for every scenario, shorting the hedge
ever more aggressively (`h -> -inf`) keeps improving every single
scenario's hedged loss without limit — there's no scenario whose sign
would eventually make that worse, so nothing stops the LP from running
to whatever `h_min` the bounds impose (found empirically while writing
this module's tests: an all-positive, perfectly-correlated synthetic
index hit the unconstrained default bound rather than any interior
optimum). A real rainfall deviation index, which genuinely takes both
signs across a multi-year scenario set, doesn't have this degeneracy —
but `LotConstraints`' bounds (from `max_order_lots`, `position_limit_lots`,
margin/notional caps) are what keep the problem well-posed in general,
not merely what keeps the answer "reasonable."
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from mq.risk.hedge import LotConstraints


@dataclass(frozen=True)
class CvarHedgeReport:
    h_star: float  # continuous LP optimum
    lots: int
    h_realized: float
    cvar_95: float  # CVaR of the realized (integer-lot) hedged loss
    do_nothing_cvar_95: float
    var_95: float


def empirical_cvar(losses: np.ndarray, alpha: float) -> float:
    """CVaR_alpha via the empirical mean of the worst (1-alpha) fraction
    of scenarios -- used both for the "do-nothing" baseline and to
    evaluate any candidate integer-lot position directly (exact, no LP
    re-solve needed per candidate)."""
    n_tail = max(1, round((1 - alpha) * len(losses)))
    worst = np.sort(losses)[-n_tail:]
    return float(np.mean(worst))


def minimize_cvar_hedge(
    exposure: np.ndarray,
    index: np.ndarray,
    *,
    multiplier: float,
    alpha: float = 0.95,
    constraints: LotConstraints | None = None,
    lot_search_radius: int = 3,
) -> CvarHedgeReport:
    if len(exposure) != len(index):
        raise ValueError("exposure and index must have the same length")
    n = len(exposure)
    if n < 2:
        raise ValueError("need at least 2 scenarios")
    constraints = constraints or LotConstraints()
    min_lots, max_lots = constraints.lot_bounds()
    h_min, h_max = min_lots * multiplier, max_lots * multiplier

    # variables z = [h, zeta, u_1..u_N]
    n_vars = 2 + n
    c = np.zeros(n_vars)
    c[1] = 1.0
    c[2:] = 1.0 / ((1 - alpha) * n)

    # u_i >= L_i + h*X_i - zeta  <=>  h*X_i - zeta - u_i <= -L_i
    A_ub = np.zeros((n, n_vars))
    A_ub[:, 0] = index
    A_ub[:, 1] = -1.0
    for i in range(n):
        A_ub[i, 2 + i] = -1.0
    b_ub = -exposure

    bounds = [(h_min, h_max), (None, None)] + [(0, None)] * n

    result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if not result.success or result.x is None:
        raise RuntimeError(f"CVaR LP failed to solve: {result.message}")
    h_star = float(result.x[0])

    center_lots = round(h_star / multiplier) if multiplier != 0 else 0
    candidates = [
        lots
        for lots in range(center_lots - lot_search_radius, center_lots + lot_search_radius + 1)
        if min_lots <= lots <= max_lots
    ]
    if not candidates:
        candidates = [int(np.clip(center_lots, min_lots, max_lots))]

    best_lots = candidates[0]
    best_cvar = empirical_cvar(exposure + best_lots * multiplier * index, alpha)
    for lots in candidates[1:]:
        cvar = empirical_cvar(exposure + lots * multiplier * index, alpha)
        if cvar < best_cvar:
            best_lots, best_cvar = lots, cvar

    h_realized = best_lots * multiplier
    hedged_losses = exposure + h_realized * index
    var_95 = float(np.quantile(hedged_losses, alpha))

    return CvarHedgeReport(
        h_star=h_star,
        lots=best_lots,
        h_realized=h_realized,
        cvar_95=best_cvar,
        do_nothing_cvar_95=empirical_cvar(exposure, alpha),
        var_95=var_95,
    )
