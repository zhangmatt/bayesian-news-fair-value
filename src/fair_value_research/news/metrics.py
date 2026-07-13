"""CLI entry point for fixture replay metrics."""

from __future__ import annotations

from pathlib import Path

from fair_value_research.news.evaluation import MetricsResult, evaluate_events
from fair_value_research.news.ingestion import FixtureNewsClient
from fair_value_research.news.market_data import FixtureMarketDataClient

REPO_ROOT = Path(__file__).resolve().parents[3]
METRICS_PATH = REPO_ROOT / "metrics.md"


def run_fixture_metrics() -> MetricsResult:
    events = FixtureMarketDataClient().load_contracts()
    news = FixtureNewsClient().load_all()
    return evaluate_events(events, news)


def write_metrics_markdown(result: MetricsResult, path: str | Path = METRICS_PATH) -> None:
    verdict = (
        "The posterior beats the market on this fixture replay."
        if result.posterior_beats_market
        else "The posterior does not beat the market on this fixture replay."
    )
    lines = [
        "# Metrics Report",
        "",
        verdict,
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Events analyzed | {result.events_analyzed} |",
        f"| News items processed | {result.news_items_processed} |",
        f"| Brier, market | {result.brier_market:.4f} |",
        f"| Brier, posterior | {result.brier_posterior:.4f} |",
        f"| Brier, 50/50 blend | {result.brier_blend:.4f} |",
        f"| Calibration error | {result.calibration_error:.4f} |",
        f"| Divergence hit-rate | {result.divergence_hit_rate:.4f} |",
        f"| Flagged divergences | {result.flagged_divergences} |",
        "",
        "## Event Replay",
        "",
        "| Event | Outcome | Market | Posterior | Blend | Gap | Flagged | News |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for row in result.evaluations:
        lines.append(
            f"| {row.event_id} | {row.outcome} | {row.market_probability:.3f} | "
            f"{row.posterior_probability:.3f} | {row.blend_probability:.3f} | "
            f"{row.signal_gap:.3f} | {row.flagged} | {row.news_items_used} |"
        )
    lines.extend(
        [
            "",
            "This fixture is small and exists to verify the replay plumbing, not to claim live edge.",
            "A real research run needs many resolved markets and archived point-in-time market/news snapshots.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    result = run_fixture_metrics()
    print(result.resume_line())
    write_metrics_markdown(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
