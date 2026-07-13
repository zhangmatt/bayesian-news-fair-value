"""Bayesian updater for binary event probabilities."""

from __future__ import annotations

from dataclasses import dataclass

from fair_value_research.news.models import EventContract, PosteriorUpdate, SentimentAggregate


@dataclass(frozen=True)
class BetaState:
    alpha: float
    beta: float

    @classmethod
    def from_probability(cls, probability: float, strength: float) -> "BetaState":
        if strength <= 0:
            raise ValueError("strength must be positive")
        p = min(1.0 - 1e-9, max(1e-9, probability))
        return cls(alpha=p * strength, beta=(1.0 - p) * strength)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def update(self, yes_pseudo_count: float, no_pseudo_count: float) -> "BetaState":
        return BetaState(
            alpha=self.alpha + max(0.0, yes_pseudo_count),
            beta=self.beta + max(0.0, no_pseudo_count),
        )


class BayesianUpdater:
    """Map stance evidence into fractional Beta pseudo-observations."""

    def __init__(self, prior_strength: float = 20.0, update_strength: float = 2.0) -> None:
        self.prior_strength = prior_strength
        self.update_strength = update_strength

    def prior_from_market(self, event: EventContract) -> BetaState:
        return BetaState.from_probability(event.implied_probability, self.prior_strength)

    def update(
        self,
        event: EventContract,
        aggregate: SentimentAggregate,
        prior: BetaState | None = None,
    ) -> PosteriorUpdate:
        prior_state = prior or self.prior_from_market(event)
        # The likelihood mapping is deliberately conservative: weighted YES
        # stance contributes fractional successes, weighted NO stance contributes
        # fractional failures. Neutral text is retained for diagnostics but does
        # not move the posterior.
        yes_count = self.update_strength * aggregate.yes_evidence
        no_count = self.update_strength * aggregate.no_evidence
        posterior = prior_state.update(yes_count, no_count)
        return PosteriorUpdate(
            event_id=event.event_id,
            prior_alpha=prior_state.alpha,
            prior_beta=prior_state.beta,
            posterior_alpha=posterior.alpha,
            posterior_beta=posterior.beta,
            yes_pseudo_count=yes_count,
            no_pseudo_count=no_count,
            update_strength=self.update_strength,
        )

    def sequential_update(
        self,
        event: EventContract,
        aggregates: list[SentimentAggregate],
    ) -> list[PosteriorUpdate]:
        updates: list[PosteriorUpdate] = []
        state = self.prior_from_market(event)
        for aggregate in sorted(aggregates, key=lambda item: item.as_of):
            update = self.update(event, aggregate, prior=state)
            updates.append(update)
            state = BetaState(update.posterior_alpha, update.posterior_beta)
        return updates

    def sensitivity(
        self,
        event: EventContract,
        aggregate: SentimentAggregate,
        strengths: list[float],
    ) -> dict[float, float]:
        values: dict[float, float] = {}
        for strength in strengths:
            updater = BayesianUpdater(self.prior_strength, strength)
            values[strength] = updater.update(event, aggregate).posterior_probability
        return values
