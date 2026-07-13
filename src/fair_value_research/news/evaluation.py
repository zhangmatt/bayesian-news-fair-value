"""Point-in-time replay and scoring metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from fair_value_research.news.bayes import BayesianUpdater
from fair_value_research.news.ingestion import item_matches_event
from fair_value_research.news.models import EventContract, EventEvaluation, NewsItem
from fair_value_research.news.sentiment import StanceClassifier, aggregate_stance
from fair_value_research.news.signals import generate_signal


@dataclass(frozen=True)
class MetricsResult:
    events_analyzed: int
    news_items_processed: int
    brier_market: float
    brier_posterior: float
    brier_blend: float
    calibration_error: float
    divergence_hit_rate: float
    flagged_divergences: int
    evaluations: list[EventEvaluation]

    @property
    def posterior_beats_market(self) -> bool:
        return self.brier_posterior < self.brier_market

    def resume_line(self) -> str:
        return (
            "RESUME_METRICS "
            f"events_analyzed={self.events_analyzed} "
            f"news_items_processed={self.news_items_processed} "
            f"brier_market={self.brier_market:.6f} "
            f"brier_posterior={self.brier_posterior:.6f} "
            f"brier_blend={self.brier_blend:.6f} "
            f"calibration_error={self.calibration_error:.6f} "
            f"divergence_hit_rate={self.divergence_hit_rate:.6f}"
        )


def evaluate_events(
    events: Iterable[EventContract],
    news_items: Iterable[NewsItem],
    updater: BayesianUpdater | None = None,
    classifier: StanceClassifier | None = None,
    threshold: float = 0.05,
    blend_weight: float = 0.50,
) -> MetricsResult:
    updater = updater or BayesianUpdater()
    all_news = list(news_items)
    evaluations: list[EventEvaluation] = []

    for event in events:
        if event.outcome is None:
            continue
        as_of = _forecast_time(event)
        replay_news = [
            item
            for item in all_news
            if (item.event_id in (None, event.event_id))
            and item.published_at <= as_of
            and item.point_in_time_at <= as_of
            and item_matches_event(item, event)
        ]
        aggregate, _scores = aggregate_stance(replay_news, event, as_of, classifier=classifier)
        update = updater.update(event, aggregate)
        signal = generate_signal(event, update, threshold=threshold)
        posterior = update.posterior_probability
        market = event.implied_probability
        blend = blend_weight * posterior + (1.0 - blend_weight) * market
        evaluations.append(
            EventEvaluation(
                event_id=event.event_id,
                question=event.question,
                outcome=event.outcome,
                market_probability=market,
                posterior_probability=posterior,
                blend_probability=blend,
                signal_gap=signal.gap,
                flagged=signal.flagged,
                news_items_used=aggregate.item_count,
            )
        )

    if not evaluations:
        return MetricsResult(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, [])

    market_predictions = [row.market_probability for row in evaluations]
    posterior_predictions = [row.posterior_probability for row in evaluations]
    blend_predictions = [row.blend_probability for row in evaluations]
    outcomes = [row.outcome for row in evaluations]
    flagged = [row for row in evaluations if row.flagged]
    hits = [row for row in flagged if row.divergence_hit]
    return MetricsResult(
        events_analyzed=len(evaluations),
        news_items_processed=sum(row.news_items_used for row in evaluations),
        brier_market=brier_score(market_predictions, outcomes),
        brier_posterior=brier_score(posterior_predictions, outcomes),
        brier_blend=brier_score(blend_predictions, outcomes),
        calibration_error=calibration_error(posterior_predictions, outcomes),
        divergence_hit_rate=0.0 if not flagged else len(hits) / len(flagged),
        flagged_divergences=len(flagged),
        evaluations=evaluations,
    )


def brier_score(predictions: list[float], outcomes: list[int]) -> float:
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must have the same length")
    if not predictions:
        return 0.0
    return sum((p - y) ** 2 for p, y in zip(predictions, outcomes, strict=True)) / len(predictions)


def calibration_error(predictions: list[float], outcomes: list[int], bins: int = 5) -> float:
    if not predictions:
        return 0.0
    bucketed: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for prediction, outcome in zip(predictions, outcomes, strict=True):
        index = min(bins - 1, int(prediction * bins))
        bucketed[index].append((prediction, outcome))
    error = 0.0
    total = len(predictions)
    for bucket in bucketed:
        if not bucket:
            continue
        mean_prediction = sum(row[0] for row in bucket) / len(bucket)
        mean_outcome = sum(row[1] for row in bucket) / len(bucket)
        error += len(bucket) / total * abs(mean_prediction - mean_outcome)
    return error


def _forecast_time(event: EventContract) -> datetime:
    return event.as_of or event.close_time
