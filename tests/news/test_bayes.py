import unittest

from fair_value_research.news.bayes import BayesianUpdater, BetaState
from fair_value_research.news.ingestion import FixtureNewsClient
from fair_value_research.news.market_data import FixtureMarketDataClient
from fair_value_research.news.sentiment import aggregate_stance


class BayesianUpdaterTests(unittest.TestCase):
    def test_beta_prior_mean_matches_market_probability(self):
        state = BetaState.from_probability(0.63, strength=20)
        self.assertAlmostEqual(state.mean, 0.63)

    def test_no_stance_update_keeps_prior(self):
        event = FixtureMarketDataClient().get_contract("kalshi-fed-cut-jun-2024")
        updater = BayesianUpdater(prior_strength=20, update_strength=2)
        aggregate, _ = aggregate_stance([], event, event.as_of)
        update = updater.update(event, aggregate)
        self.assertAlmostEqual(update.posterior_probability, event.implied_probability)

    def test_sequential_update_uses_previous_posterior(self):
        event = FixtureMarketDataClient().get_contract("kalshi-fed-cut-jun-2024")
        news = FixtureNewsClient().fetch(event, event.as_of)
        aggregate, _ = aggregate_stance(news, event, event.as_of)
        updater = BayesianUpdater(prior_strength=20, update_strength=2)
        updates = updater.sequential_update(event, [aggregate, aggregate])
        self.assertEqual(len(updates), 2)
        self.assertAlmostEqual(updates[0].posterior_alpha, updates[1].prior_alpha)
        self.assertAlmostEqual(updates[0].posterior_beta, updates[1].prior_beta)


if __name__ == "__main__":
    unittest.main()
