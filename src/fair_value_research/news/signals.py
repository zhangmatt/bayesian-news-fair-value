"""Signal generation from posterior minus market-implied probability."""

from __future__ import annotations

from fair_value_research.news.models import EventContract, PosteriorUpdate, Signal


def generate_signal(
    event: EventContract,
    update: PosteriorUpdate,
    threshold: float = 0.05,
) -> Signal:
    posterior = update.posterior_probability
    market = event.implied_probability
    return Signal(
        event_id=event.event_id,
        market_probability=market,
        posterior_probability=posterior,
        gap=posterior - market,
        threshold=threshold,
    )
