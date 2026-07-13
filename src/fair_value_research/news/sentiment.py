"""Stance classification and evidence aggregation."""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Protocol

from fair_value_research.news.models import EventContract, NewsItem, SentimentAggregate, StanceScore

DEFAULT_SOURCE_WEIGHTS = {
    "reuters": 1.25,
    "associated press": 1.20,
    "ap": 1.20,
    "federal reserve": 1.30,
    "sec": 1.30,
    "government": 1.15,
    "company filing": 1.25,
    "major newspaper": 1.05,
    "blog": 0.70,
    "x": 0.50,
    "social": 0.50,
}


class StanceClassifier(Protocol):
    def classify(self, item: NewsItem, event: EventContract) -> StanceScore:
        ...


class LexiconStanceClassifier:
    """Transparent fallback classifier for offline replay and tests."""

    yes_hints = (
        "approve",
        "approved",
        "approval",
        "likely",
        "will",
        "clear path",
        "green light",
        "passes",
        "support",
        "confirm",
        "above forecast",
        "hot inflation",
        "rate cut",
        "dovish",
    )
    no_hints = (
        "unlikely",
        "delay",
        "delayed",
        "reject",
        "rejected",
        "blocked",
        "scrutiny",
        "risk",
        "fails",
        "hold rates",
        "higher for longer",
        "below forecast",
        "cooling inflation",
        "deal reached",
    )

    def classify(self, item: NewsItem, event: EventContract) -> StanceScore:
        text = item.text.lower()
        yes_terms = tuple(dict.fromkeys(event.yes_terms + self.yes_hints))
        no_terms = tuple(dict.fromkeys(event.no_terms + self.no_hints))
        yes_raw = _term_score(text, yes_terms)
        no_raw = _term_score(text, no_terms)

        if yes_raw == no_raw:
            stance = "neutral"
            confidence = 0.55
            rationale = "balanced or no directional terms"
        elif yes_raw > no_raw:
            stance = "yes"
            confidence = _confidence(yes_raw, no_raw)
            rationale = f"yes_terms={yes_raw:.2f} no_terms={no_raw:.2f}"
        else:
            stance = "no"
            confidence = _confidence(no_raw, yes_raw)
            rationale = f"yes_terms={yes_raw:.2f} no_terms={no_raw:.2f}"

        total = yes_raw + no_raw
        yes_score = 0.0 if total == 0 else yes_raw / total
        no_score = 0.0 if total == 0 else no_raw / total
        neutral_score = 1.0 if total == 0 else max(0.0, 1.0 - abs(yes_score - no_score))
        return StanceScore(
            item_id=item.item_id,
            event_id=event.event_id,
            stance=stance,
            confidence=confidence,
            yes_score=yes_score,
            no_score=no_score,
            neutral_score=neutral_score,
            source_weight=1.0,
            recency_weight=1.0,
            evidence_weight=0.0,
            rationale=rationale,
        )


class ZeroShotStanceClassifier:
    """Optional pretrained NLI stance classifier.

    This keeps the task as stance classification by asking whether the text
    supports the YES resolution, supports the NO resolution, or is neutral.
    It requires the optional transformers stack and is not used by offline tests.
    """

    def __init__(self, model_name: str = "facebook/bart-large-mnli") -> None:
        from transformers import pipeline

        self.pipeline = pipeline("zero-shot-classification", model=model_name)

    def classify(self, item: NewsItem, event: EventContract) -> StanceScore:
        labels = [
            f"supports YES: {event.question}",
            f"supports NO: {event.question}",
            "neutral or unrelated",
        ]
        result = self.pipeline(item.text[:3000], labels)
        label_scores = dict(zip(result["labels"], result["scores"], strict=False))
        yes_score = float(label_scores.get(labels[0], 0.0))
        no_score = float(label_scores.get(labels[1], 0.0))
        neutral_score = float(label_scores.get(labels[2], 0.0))
        if neutral_score >= max(yes_score, no_score):
            stance = "neutral"
            confidence = neutral_score
        elif yes_score > no_score:
            stance = "yes"
            confidence = yes_score
        else:
            stance = "no"
            confidence = no_score
        return StanceScore(
            item_id=item.item_id,
            event_id=event.event_id,
            stance=stance,
            confidence=confidence,
            yes_score=yes_score,
            no_score=no_score,
            neutral_score=neutral_score,
            source_weight=1.0,
            recency_weight=1.0,
            evidence_weight=0.0,
            rationale="zero-shot NLI stance",
        )


def aggregate_stance(
    items: list[NewsItem],
    event: EventContract,
    as_of: datetime,
    classifier: StanceClassifier | None = None,
    half_life_hours: float = 72.0,
    source_weights: dict[str, float] | None = None,
) -> tuple[SentimentAggregate, list[StanceScore]]:
    classifier = classifier or LexiconStanceClassifier()
    weights = source_weights or DEFAULT_SOURCE_WEIGHTS
    yes_evidence = 0.0
    no_evidence = 0.0
    neutral_evidence = 0.0
    weighted_count = 0.0
    scores: list[StanceScore] = []

    for item in items:
        if item.published_at > as_of or item.point_in_time_at > as_of:
            continue
        raw_score = classifier.classify(item, event)
        source_weight = source_quality_weight(item.source, weights)
        recency = recency_weight(item.published_at, as_of, half_life_hours)
        evidence_weight = raw_score.confidence * source_weight * recency
        score = StanceScore(
            item_id=raw_score.item_id,
            event_id=raw_score.event_id,
            stance=raw_score.stance,
            confidence=raw_score.confidence,
            yes_score=raw_score.yes_score,
            no_score=raw_score.no_score,
            neutral_score=raw_score.neutral_score,
            source_weight=source_weight,
            recency_weight=recency,
            evidence_weight=evidence_weight,
            rationale=raw_score.rationale,
        )
        scores.append(score)
        weighted_count += evidence_weight
        if score.stance == "yes":
            yes_evidence += evidence_weight
        elif score.stance == "no":
            no_evidence += evidence_weight
        else:
            neutral_evidence += evidence_weight

    aggregate = SentimentAggregate(
        event_id=event.event_id,
        as_of=as_of,
        yes_evidence=yes_evidence,
        no_evidence=no_evidence,
        neutral_evidence=neutral_evidence,
        item_count=len(scores),
        weighted_item_count=weighted_count,
    )
    return aggregate, scores


def source_quality_weight(source: str, weights: dict[str, float] | None = None) -> float:
    weights = weights or DEFAULT_SOURCE_WEIGHTS
    normalized = source.lower()
    for key, weight in weights.items():
        if key in normalized:
            return weight
    return 1.0


def recency_weight(published_at: datetime, as_of: datetime, half_life_hours: float) -> float:
    age_hours = max(0.0, (as_of - published_at).total_seconds() / 3600.0)
    if half_life_hours <= 0:
        return 1.0
    return 0.5 ** (age_hours / half_life_hours)


def _term_score(text: str, terms: tuple[str, ...]) -> float:
    score = 0.0
    for term in terms:
        normalized = term.lower().strip()
        if not normalized:
            continue
        occurrences = len(re.findall(rf"(?<!\w){re.escape(normalized)}(?!\w)", text))
        if occurrences:
            score += occurrences * (1.5 if " " in normalized else 1.0)
    return score


def _confidence(winner: float, loser: float) -> float:
    margin = winner - loser
    scale = winner + loser + 1.0
    return min(0.95, max(0.55, 0.55 + 0.40 * math.tanh(margin / scale * 2.0)))
