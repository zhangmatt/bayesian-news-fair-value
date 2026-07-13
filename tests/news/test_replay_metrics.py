import unittest

from fair_value_research.news.evaluation import evaluate_events
from fair_value_research.news.ingestion import FixtureNewsClient
from fair_value_research.news.market_data import FixtureMarketDataClient
from fair_value_research.news.models import NewsItem


class ReplayMetricsTests(unittest.TestCase):
    def test_future_news_is_ignored(self):
        events = FixtureMarketDataClient().load_contracts()
        eth_event = [event for event in events if event.event_id == "polymarket-eth-etf-may-2024"][0]
        news = FixtureNewsClient().fetch(eth_event, eth_event.as_of)
        ids = {item.item_id for item in news}
        self.assertNotIn("eth-future-001", ids)

    def test_fixture_metrics_are_deterministic(self):
        events = FixtureMarketDataClient().load_contracts()
        news = FixtureNewsClient().load_all()
        result = evaluate_events(events, news)
        self.assertEqual(result.events_analyzed, 4)
        self.assertEqual(result.news_items_processed, 8)
        self.assertGreaterEqual(result.divergence_hit_rate, 0.0)
        self.assertLessEqual(result.divergence_hit_rate, 1.0)

    def test_unassigned_unrelated_news_is_not_scored(self):
        events = FixtureMarketDataClient().load_contracts()
        event = events[0]
        unrelated = NewsItem(
            item_id="unrelated",
            event_id=None,
            source="Reuters",
            title="Completely unrelated commodity story",
            body="Copper inventories rose in warehouses.",
            published_at=event.as_of,
            point_in_time_at=event.as_of,
        )
        result = evaluate_events([event], [unrelated])
        self.assertEqual(result.news_items_processed, 0)


if __name__ == "__main__":
    unittest.main()
