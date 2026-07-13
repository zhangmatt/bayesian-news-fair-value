"""Bayesian news/sentiment fair-value engine for binary event contracts."""

from fair_value_research.news.bayes import BayesianUpdater, BetaState
from fair_value_research.news.evaluation import evaluate_events
from fair_value_research.news.market_data import FixtureMarketDataClient
from fair_value_research.news.models import EventContract, NewsItem

__all__ = [
    "BayesianUpdater",
    "BetaState",
    "EventContract",
    "FixtureMarketDataClient",
    "NewsItem",
    "evaluate_events",
]
