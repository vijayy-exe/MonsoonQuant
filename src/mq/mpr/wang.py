"""Wang transform market-price-of-risk pricing (SPEC §7.5).

    F*(x) = Φ(Φ⁻¹(F(x)) - λ)     price = E_{F*}[payoff]

Implemented by reweighting an existing P-measure payoff sample — no
re-simulation, per SPEC. The sample's order statistics stand in for F:
with payoffs sorted ascending, the i-th smallest value's empirical CDF
is taken at the plotting position i/(n+1) rather than i/n — i/n would
put the largest value at F=1 exactly, where Φ⁻¹(1)=+inf blows up the
transform; i/(n+1) keeps every point strictly inside (0,1). The
Q-measure probability mass on each order statistic is then the
increment of F* across consecutive plotting positions, renormalized to
sum to 1 (the raw increments already nearly sum to 1 — i/(n+1) never
quite reaches full mass at the open right end — renormalizing makes
this an exact probability distribution rather than leaving a tiny
unaccounted sliver).

Sign convention (verified by test, not assumed from any one paper's
convention — Wang-transform literature states it both ways depending on
whether it's applied to the CDF or the survival function, and SPEC's
own formula is stated on F directly): λ>0 makes F*(x) < F(x) everywhere,
i.e. Q is the first-order-stochastically-larger distribution — so
E_Q[payoff] > E_P[payoff] for λ>0. A positive λ is a risk LOADING that
raises the price above the physical-measure mean.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def wang_weights(payoffs: np.ndarray, lam: float) -> np.ndarray:
    """Q-measure probability weight for each of `payoffs`' sorted order
    statistics. Returns weights in the SAME order as `np.sort(payoffs)`
    — pair them with `np.sort(payoffs)`, not the original array."""
    n = len(payoffs)
    f = np.arange(1, n + 1) / (n + 1)  # plotting positions, strictly in (0,1)
    f_star = stats.norm.cdf(stats.norm.ppf(f) - lam)
    f_star_padded = np.concatenate([[0.0], f_star])
    weights = np.diff(f_star_padded)
    return weights / weights.sum()  # type: ignore[no-any-return]


def wang_price(payoffs: np.ndarray, lam: float) -> float:
    sorted_payoffs = np.sort(payoffs)
    weights = wang_weights(sorted_payoffs, lam)
    return float(np.sum(weights * sorted_payoffs))
