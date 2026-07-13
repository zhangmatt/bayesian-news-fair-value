import unittest

from fair_value_research.news.live_corpus import (
    _line_relevant,
    extract_query_terms,
    gdelt_timestamp,
    google_news_query,
    parse_gdelt_seen_date,
    parse_rss_date,
    split_google_news_title,
)
from fair_value_research.news.models import EventContract


class LiveCorpusTests(unittest.TestCase):
    def test_parse_gdelt_seen_date(self):
        parsed = parse_gdelt_seen_date("20241029T120000Z")
        self.assertEqual(gdelt_timestamp(parsed), "20241029120000")

    def test_extract_query_terms_prefers_named_phrases(self):
        terms = extract_query_terms(
            "Will Donald Trump win the 2024 US Presidential Election?",
            "Presidential Election Winner 2024",
        )
        self.assertIn("Donald Trump", terms)

    def test_current_events_election_line_matches_market(self):
        event = EventContract(
            event_id="test",
            venue="polymarket",
            ticker="test",
            question="Will Donald Trump win the 2024 US Presidential Election?",
            resolution_criteria="",
            close_time="2024-11-06T00:00:00Z",
            current_price=0.6,
            keywords=("Presidential Election Winner 2024",),
            entities=("Donald Trump", "US Presidential Election"),
        )
        line = "Voters across the United States go to the polls for the 2024 presidential election."
        self.assertTrue(_line_relevant(line, event, list(event.entities)))

    def test_google_news_helpers(self):
        title, source = split_google_news_title("Trump campaign story - Reuters")
        self.assertEqual(title, "Trump campaign story")
        self.assertEqual(source, "Reuters")
        self.assertEqual(parse_rss_date("Wed, 30 Oct 2024 07:00:00 GMT").year, 2024)

    def test_google_query_for_fed_decision(self):
        event = EventContract(
            event_id="fed",
            venue="polymarket",
            ticker="fed",
            question="Fed decreases interest rates by 25 bps after January meeting?",
            resolution_criteria="",
            close_time="2026-01-28T00:00:00Z",
            current_price=0.5,
            metadata={"event_title": "Fed decision in January?"},
        )
        self.assertIn("Federal Reserve", google_news_query(event))


if __name__ == "__main__":
    unittest.main()
