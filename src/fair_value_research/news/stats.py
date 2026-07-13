"""Statistical helpers for comparing forecast losses."""

from __future__ import annotations

import random
from dataclasses import dataclass

from fair_value_research.news.models import EventEvaluation


@dataclass(frozen=True)
class BrierComparison:
    n: int
    posterior_minus_market: float
    blend_minus_market: float
    posterior_ci_low: float
    posterior_ci_high: float
    blend_ci_low: float
    blend_ci_high: float
    posterior_within_noise: bool
    blend_within_noise: bool


def paired_brier_comparison(
    evaluations: list[EventEvaluation],
    bootstrap_samples: int = 2000,
    seed: int = 7,
) -> BrierComparison:
    """Paired bootstrap CIs for Brier deltas against the market forecast."""

    n = len(evaluations)
    if n == 0:
        return BrierComparison(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, True, True)

    posterior_deltas = [row.posterior_brier - row.market_brier for row in evaluations]
    blend_deltas = [row.blend_brier - row.market_brier for row in evaluations]
    observed_posterior = sum(posterior_deltas) / n
    observed_blend = sum(blend_deltas) / n
    rng = random.Random(seed)
    posterior_samples: list[float] = []
    blend_samples: list[float] = []
    for _ in range(bootstrap_samples):
        indices = [rng.randrange(n) for _ in range(n)]
        posterior_samples.append(sum(posterior_deltas[i] for i in indices) / n)
        blend_samples.append(sum(blend_deltas[i] for i in indices) / n)

    posterior_low, posterior_high = _percentile(posterior_samples, 0.025), _percentile(
        posterior_samples, 0.975
    )
    blend_low, blend_high = _percentile(blend_samples, 0.025), _percentile(blend_samples, 0.975)
    return BrierComparison(
        n=n,
        posterior_minus_market=observed_posterior,
        blend_minus_market=observed_blend,
        posterior_ci_low=posterior_low,
        posterior_ci_high=posterior_high,
        blend_ci_low=blend_low,
        blend_ci_high=blend_high,
        posterior_within_noise=posterior_low <= 0.0 <= posterior_high,
        blend_within_noise=blend_low <= 0.0 <= blend_high,
    )


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction
