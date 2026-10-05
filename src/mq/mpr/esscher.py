"""Esscher transform market-price-of-risk pricing (SPEC §7.5).

    dQ/dP ∝ exp(θ·I)     price via self-normalised importance weights

Tilts on the STANDARDIZED payoff z = (x - mean(x)) / sd(x), not raw
payoff units (hundreds of mm of rainfall) — exp(θ·x) with θ anywhere
near O(1) and x~900 overflows a double instantly, forcing θ down into
a vanishingly small, hard-to-interpret range. Tilting on z instead is
not a different transform, just a reparameterization: exp(θ·z) =
exp(θ·(x-mean)/sd) ∝ exp((θ/sd)·x) as an importance weight (constants
drop out under self-normalization), so Esscher-on-z with parameter θ
is exactly textbook Esscher-on-x with θ_raw = θ/sd. This puts θ on the
same O(1), dimensionless scale as Wang's λ, so SPEC's
single "λ bounded in [-3, 3]" calibration bound applies to both
transforms without rescaling per-contract.

SPEC's own stated gate: refuse (not silently report) a price whose
effective sample size (ESS) falls below 1% of N — a self-normalized
importance-sampling estimate dominated by a handful of extreme weights
is not a reliable price, regardless of what number it computes to.
"""

from __future__ import annotations

import numpy as np


class LowEffectiveSampleSizeError(RuntimeError):
    """Raised when a self-normalized Esscher estimate's ESS falls below
    the required fraction of N — the weights are too concentrated on a
    few samples to trust the estimate."""


def _standardize(payoffs: np.ndarray) -> np.ndarray:
    mean = np.mean(payoffs)
    sd = np.std(payoffs, ddof=1)
    return (payoffs - mean) / sd  # type: ignore[no-any-return]


def esscher_weights(payoffs: np.ndarray, theta: float) -> np.ndarray:
    z = _standardize(payoffs)
    log_w = theta * z
    log_w -= log_w.max()  # log-sum-exp stabilization before exponentiating
    w = np.exp(log_w)
    return w / w.sum()  # type: ignore[no-any-return]


def effective_sample_size(weights: np.ndarray) -> float:
    """Kish's ESS for self-normalized weights summing to 1: 1 / sum(w^2).
    Equals N when weights are uniform (1/N each); collapses toward 1 as
    weight concentrates on a single sample."""
    return float(1.0 / np.sum(weights**2))


def esscher_price(payoffs: np.ndarray, theta: float, *, min_ess_fraction: float = 0.01) -> float:
    weights = esscher_weights(payoffs, theta)
    n = len(payoffs)
    ess = effective_sample_size(weights)
    if ess < min_ess_fraction * n:
        raise LowEffectiveSampleSizeError(
            f"ESS={ess:.1f} < {min_ess_fraction * n:.1f} "
            f"({min_ess_fraction:.0%} of n={n}) at theta={theta} — "
            "self-normalized estimate unreliable at this tilt"
        )
    return float(np.sum(weights * payoffs))
