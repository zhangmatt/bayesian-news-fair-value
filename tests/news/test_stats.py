import unittest

from fair_value_research.news.models import EventEvaluation
from fair_value_research.news.stats import paired_brier_comparison


class StatsTests(unittest.TestCase):
    def test_bootstrap_marks_exact_tie_as_noise(self):
        rows = [
            EventEvaluation("a", "A?", 1, 0.7, 0.7, 0.7, 0.0, False, 1),
            EventEvaluation("b", "B?", 0, 0.3, 0.3, 0.3, 0.0, False, 1),
        ]
        comparison = paired_brier_comparison(rows, bootstrap_samples=100)
        self.assertAlmostEqual(comparison.posterior_minus_market, 0.0)
        self.assertTrue(comparison.posterior_within_noise)


if __name__ == "__main__":
    unittest.main()
