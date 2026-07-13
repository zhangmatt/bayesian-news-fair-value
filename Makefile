.PHONY: test metrics fixture-metrics live-refresh clean

test:
	PYTHONPATH=src python3 -m pytest tests

metrics:
	PYTHONPATH=src python3 -m fair_value_research.news.live_metrics --no-rebuild

fixture-metrics:
	PYTHONPATH=src python3 -m fair_value_research.news

live-refresh:
	PYTHONPATH=src python3 -m fair_value_research.news.live_metrics --target-events 50 --max-event-pages 12 --news-source google_rss --news-lookback-days 30

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .cache
