"""Typed data models shared by market, news, sentiment, and evaluation code."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Stance = Literal["yes", "no", "neutral"]


def parse_dt(value: str | datetime | None) -> datetime | None:
    """Parse an RFC3339-ish timestamp and normalize it to UTC."""

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_probability(value: float | int | str, field_name: str = "probability") -> float:
    """Normalize common venue price formats into a [0, 1] probability."""

    probability = float(value)
    if probability > 1.0 and probability <= 100.0:
        probability = probability / 100.0
    if probability < 0.0 or probability > 1.0:
        raise ValueError(f"{field_name} must normalize to [0, 1], got {value!r}")
    return probability


def _tuple_of_str(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return (values,)
    return tuple(str(v) for v in values if str(v).strip())


@dataclass(frozen=True)
class EventContract:
    """A normalized binary YES/NO event contract snapshot."""

    event_id: str
    venue: str
    ticker: str
    question: str
    resolution_criteria: str
    close_time: datetime
    current_price: float
    implied_probability: float | None = None
    resolve_time: datetime | None = None
    as_of: datetime | None = None
    outcome: int | None = None
    keywords: tuple[str, ...] = field(default_factory=tuple)
    entities: tuple[str, ...] = field(default_factory=tuple)
    yes_terms: tuple[str, ...] = field(default_factory=tuple)
    no_terms: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        price = normalize_probability(self.current_price, "current_price")
        implied = price if self.implied_probability is None else normalize_probability(
            self.implied_probability, "implied_probability"
        )
        if self.outcome is not None and self.outcome not in (0, 1):
            raise ValueError("outcome must be 0, 1, or None")
        object.__setattr__(self, "current_price", price)
        object.__setattr__(self, "implied_probability", implied)
        object.__setattr__(self, "close_time", parse_dt(self.close_time))
        object.__setattr__(self, "resolve_time", parse_dt(self.resolve_time))
        object.__setattr__(self, "as_of", parse_dt(self.as_of))
        object.__setattr__(self, "keywords", _tuple_of_str(self.keywords))
        object.__setattr__(self, "entities", _tuple_of_str(self.entities))
        object.__setattr__(self, "yes_terms", _tuple_of_str(self.yes_terms))
        object.__setattr__(self, "no_terms", _tuple_of_str(self.no_terms))

    @property
    def event_terms(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.keywords + self.entities + (self.ticker,)))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventContract":
        return cls(
            event_id=str(data["event_id"]),
            venue=str(data["venue"]),
            ticker=str(data.get("ticker", data["event_id"])),
            question=str(data["question"]),
            resolution_criteria=str(data.get("resolution_criteria", "")),
            close_time=parse_dt(data.get("close_time") or data.get("close_date")),
            resolve_time=parse_dt(data.get("resolve_time") or data.get("resolve_date")),
            as_of=parse_dt(data.get("as_of") or data.get("last_price_time")),
            current_price=data.get("current_price", data.get("price", data.get("yes_price", 0.5))),
            implied_probability=data.get("implied_probability"),
            outcome=data.get("outcome"),
            keywords=_tuple_of_str(data.get("keywords")),
            entities=_tuple_of_str(data.get("entities")),
            yes_terms=_tuple_of_str(data.get("yes_terms")),
            no_terms=_tuple_of_str(data.get("no_terms")),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "venue": self.venue,
            "ticker": self.ticker,
            "question": self.question,
            "resolution_criteria": self.resolution_criteria,
            "close_time": dt_to_iso(self.close_time),
            "resolve_time": dt_to_iso(self.resolve_time),
            "as_of": dt_to_iso(self.as_of),
            "current_price": self.current_price,
            "implied_probability": self.implied_probability,
            "outcome": self.outcome,
            "keywords": list(self.keywords),
            "entities": list(self.entities),
            "yes_terms": list(self.yes_terms),
            "no_terms": list(self.no_terms),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class NewsItem:
    """A timestamped text item as observed by the ingestion system."""

    item_id: str
    event_id: str | None
    source: str
    title: str
    body: str
    published_at: datetime
    point_in_time_at: datetime
    url: str | None = None
    matched_terms: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "published_at", parse_dt(self.published_at))
        object.__setattr__(self, "point_in_time_at", parse_dt(self.point_in_time_at))
        object.__setattr__(self, "matched_terms", _tuple_of_str(self.matched_terms))

    @property
    def text(self) -> str:
        return " ".join(part for part in (self.title, self.body) if part).strip()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NewsItem":
        return cls(
            item_id=str(data["item_id"]),
            event_id=data.get("event_id"),
            source=str(data.get("source", "unknown")),
            title=str(data.get("title", "")),
            body=str(data.get("body", "")),
            published_at=parse_dt(data["published_at"]),
            point_in_time_at=parse_dt(data.get("point_in_time_at", data["published_at"])),
            url=data.get("url"),
            matched_terms=_tuple_of_str(data.get("matched_terms")),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "event_id": self.event_id,
            "source": self.source,
            "title": self.title,
            "body": self.body,
            "published_at": dt_to_iso(self.published_at),
            "point_in_time_at": dt_to_iso(self.point_in_time_at),
            "url": self.url,
            "matched_terms": list(self.matched_terms),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class StanceScore:
    item_id: str
    event_id: str
    stance: Stance
    confidence: float
    yes_score: float
    no_score: float
    neutral_score: float
    source_weight: float
    recency_weight: float
    evidence_weight: float
    rationale: str = ""

    @property
    def signed_evidence(self) -> float:
        if self.stance == "yes":
            return self.evidence_weight
        if self.stance == "no":
            return -self.evidence_weight
        return 0.0


@dataclass(frozen=True)
class SentimentAggregate:
    event_id: str
    as_of: datetime
    yes_evidence: float
    no_evidence: float
    neutral_evidence: float
    item_count: int
    weighted_item_count: float

    @property
    def net_stance(self) -> float:
        total = self.yes_evidence + self.no_evidence
        if total == 0:
            return 0.0
        return (self.yes_evidence - self.no_evidence) / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "as_of": dt_to_iso(self.as_of),
            "yes_evidence": self.yes_evidence,
            "no_evidence": self.no_evidence,
            "neutral_evidence": self.neutral_evidence,
            "item_count": self.item_count,
            "weighted_item_count": self.weighted_item_count,
            "net_stance": self.net_stance,
        }


@dataclass(frozen=True)
class PosteriorUpdate:
    event_id: str
    prior_alpha: float
    prior_beta: float
    posterior_alpha: float
    posterior_beta: float
    yes_pseudo_count: float
    no_pseudo_count: float
    update_strength: float

    @property
    def prior_probability(self) -> float:
        return self.prior_alpha / (self.prior_alpha + self.prior_beta)

    @property
    def posterior_probability(self) -> float:
        return self.posterior_alpha / (self.posterior_alpha + self.posterior_beta)

    @property
    def effective_sample_size(self) -> float:
        return self.posterior_alpha + self.posterior_beta


@dataclass(frozen=True)
class Signal:
    event_id: str
    market_probability: float
    posterior_probability: float
    gap: float
    threshold: float

    @property
    def direction(self) -> str:
        if abs(self.gap) < self.threshold:
            return "hold"
        return "buy_yes" if self.gap > 0 else "buy_no"

    @property
    def flagged(self) -> bool:
        return self.direction != "hold"


@dataclass(frozen=True)
class EventEvaluation:
    event_id: str
    question: str
    outcome: int
    market_probability: float
    posterior_probability: float
    blend_probability: float
    signal_gap: float
    flagged: bool
    news_items_used: int

    @property
    def market_brier(self) -> float:
        return (self.market_probability - self.outcome) ** 2

    @property
    def posterior_brier(self) -> float:
        return (self.posterior_probability - self.outcome) ** 2

    @property
    def blend_brier(self) -> float:
        return (self.blend_probability - self.outcome) ** 2

    @property
    def divergence_hit(self) -> bool:
        if not self.flagged:
            return False
        return self.posterior_brier < self.market_brier
