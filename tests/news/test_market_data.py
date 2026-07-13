import unittest

from fair_value_research.news.market_data import (
    FixtureMarketDataClient,
    extract_kalshi_yes_probability,
    normalize_implied_probability,
)


class MarketDataTests(unittest.TestCase):
    def test_normalizes_cents_and_probabilities(self):
        self.assertAlmostEqual(normalize_implied_probability(56), 0.56)
        self.assertAlmostEqual(normalize_implied_probability("0.42"), 0.42)

    def test_loads_fixture_contracts(self):
        contracts = FixtureMarketDataClient().load_contracts()
        self.assertEqual(len(contracts), 4)
        self.assertTrue(all(0.0 <= contract.implied_probability <= 1.0 for contract in contracts))

    def test_extracts_kalshi_midpoint(self):
        market = {"ticker": "TEST", "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.44"}
        self.assertAlmostEqual(extract_kalshi_yes_probability(market), 0.42)


if __name__ == "__main__":
    unittest.main()
