import unittest

from fair_value_research.news.ingestion import FixtureNewsClient
from fair_value_research.news.market_data import FixtureMarketDataClient
from fair_value_research.news.sentiment import LexiconStanceClassifier, aggregate_stance


class SentimentTests(unittest.TestCase):
    def test_classifies_no_stance_toward_fed_cut(self):
        event = FixtureMarketDataClient().get_contract("kalshi-fed-cut-jun-2024")
        item = FixtureNewsClient().fetch(event, event.as_of)[0]
        score = LexiconStanceClassifier().classify(item, event)
        self.assertEqual(score.stance, "no")

    def test_aggregates_weighted_evidence(self):
        event = FixtureMarketDataClient().get_contract("kalshi-fed-cut-jun-2024")
        news = FixtureNewsClient().fetch(event, event.as_of)
        aggregate, scores = aggregate_stance(news, event, event.as_of)
        self.assertEqual(len(scores), 2)
        self.assertGreater(aggregate.no_evidence, aggregate.yes_evidence)


if __name__ == "__main__":
    unittest.main()
