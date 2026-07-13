"""CLI for live-corpus evaluation and metrics report generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from fair_value_research.news.evaluation import MetricsResult, evaluate_events
from fair_value_research.news.live_corpus import LIVE_MANIFEST_PATH, build_live_corpus, load_live_corpus
from fair_value_research.news.metrics import METRICS_PATH
from fair_value_research.news.sentiment import aggregate_stance
from fair_value_research.news.stats import BrierComparison, paired_brier_comparison
from fair_value_research.news.storage import read_json


def run_live_metrics(
    target_events: int = 50,
    max_event_pages: int = 12,
    market_lookback_days: int = 1,
    news_lookback_days: int = 30,
    news_source: str = "auto",
    allow_wikipedia_fallback: bool = False,
    refresh: bool = False,
    rebuild: bool = True,
) -> tuple[MetricsResult, BrierComparison, dict]:
    if rebuild:
        corpus = build_live_corpus(
            target_events=target_events,
            max_event_pages=max_event_pages,
            market_lookback_days=market_lookback_days,
            news_lookback_days=news_lookback_days,
            news_source=news_source,
            allow_wikipedia_fallback=allow_wikipedia_fallback,
            refresh=refresh,
        )
        events, news, manifest = corpus.events, corpus.news, corpus.manifest
    else:
        events, news = load_live_corpus()
        manifest = read_json(LIVE_MANIFEST_PATH)
    result = evaluate_events(events, news)
    comparison = paired_brier_comparison(result.evaluations)
    stances = stance_distribution(events, news)
    write_live_metrics_markdown(result, comparison, manifest, stances)
    return result, comparison, manifest


def stance_distribution(events, news) -> dict[str, int]:
    counts = {"yes": 0, "no": 0, "neutral": 0}
    for event in events:
        as_of = event.as_of or event.close_time
        event_news = [item for item in news if item.event_id == event.event_id]
        _aggregate, scores = aggregate_stance(event_news, event, as_of)
        for score in scores:
            counts[score.stance] += 1
    return counts


def write_live_metrics_markdown(
    result: MetricsResult,
    comparison: BrierComparison,
    manifest: dict,
    stances: dict[str, int],
    path: str | Path = METRICS_PATH,
) -> None:
    if comparison.posterior_within_noise:
        posterior_noise = "within noise"
    else:
        posterior_noise = "outside the bootstrap noise band"
    if comparison.blend_within_noise:
        blend_noise = "within noise"
    else:
        blend_noise = "outside the bootstrap noise band"

    if result.brier_posterior < result.brier_market:
        verdict = "The posterior has a lower Brier score than the market in this run."
    elif result.brier_posterior > result.brier_market:
        verdict = "The posterior has a higher Brier score than the market in this run."
    else:
        verdict = "The posterior ties the market Brier score in this run."

    lines = [
        "# Metrics Report",
        "",
        verdict,
        (
            f"The posterior-minus-market Brier delta is "
            f"{comparison.posterior_minus_market:+.6f} with a paired bootstrap 95% CI "
            f"[{comparison.posterior_ci_low:+.6f}, {comparison.posterior_ci_high:+.6f}], "
            f"so the difference is {posterior_noise} for n={comparison.n}."
        ),
        (
            f"The blend-minus-market Brier delta is {comparison.blend_minus_market:+.6f} "
            f"with 95% CI [{comparison.blend_ci_low:+.6f}, {comparison.blend_ci_high:+.6f}], "
            f"so the blend difference is {blend_noise}."
        ),
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Events analyzed | {result.events_analyzed} |",
        f"| News items processed | {result.news_items_processed} |",
        f"| Brier, market | {result.brier_market:.6f} |",
        f"| Brier, posterior | {result.brier_posterior:.6f} |",
        f"| Brier, 50/50 blend | {result.brier_blend:.6f} |",
        f"| Calibration error | {result.calibration_error:.6f} |",
        f"| Divergence hit-rate | {result.divergence_hit_rate:.6f} |",
        f"| Flagged divergences | {result.flagged_divergences} |",
        f"| YES stances | {stances.get('yes', 0)} |",
        f"| NO stances | {stances.get('no', 0)} |",
        f"| Neutral stances | {stances.get('neutral', 0)} |",
        f"| Posterior-market delta | {comparison.posterior_minus_market:+.6f} |",
        f"| Posterior-market 95% CI low | {comparison.posterior_ci_low:+.6f} |",
        f"| Posterior-market 95% CI high | {comparison.posterior_ci_high:+.6f} |",
        f"| Blend-market delta | {comparison.blend_minus_market:+.6f} |",
        f"| Blend-market 95% CI low | {comparison.blend_ci_low:+.6f} |",
        f"| Blend-market 95% CI high | {comparison.blend_ci_high:+.6f} |",
        "",
        "## Corpus",
        "",
        f"- Source: {manifest.get('source')}",
        f"- Built at: {manifest.get('built_at')}",
        f"- Market forecast snapshot: {manifest.get('market_lookback_days')} days before close, using the latest CLOB history point at or before that time.",
        f"- News window: {manifest.get('news_lookback_days')} days before the market as-of timestamp.",
        f"- News source requested: `{manifest.get('news_source_requested')}`",
        f"- Wikipedia fallback allowed: `{manifest.get('allow_wikipedia_fallback')}`",
        f"- No-lookahead rule: {manifest.get('no_lookahead_rule')}",
        f"- Disabled hosts during run: `{manifest.get('disabled_hosts', [])}`",
        f"- Skipped candidates: `{manifest.get('skipped')}`",
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
    source_requested = manifest.get("news_source_requested")
    if source_requested == "google_rss":
        corpus_note = (
            "Interpretation: this replay uses date-bounded Google News RSS headlines/snippets. "
            "That is a genuine news corpus, but pubDate is weaker than GDELT's first-seen timestamp."
        )
    elif source_requested == "gdelt":
        corpus_note = "Interpretation: this replay uses GDELT DOC 2.0 article titles with first-seen timestamps."
    else:
        corpus_note = "Interpretation: this replay uses the configured live news source mix recorded above."
    lines.extend(
        [
            "",
            corpus_note,
            "Treat the bootstrap interval as a noise check, not a full inference procedure for market dependence or parameter selection.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/evaluate a live historical corpus.")
    parser.add_argument("--target-events", type=int, default=50)
    parser.add_argument("--max-event-pages", type=int, default=12)
    parser.add_argument("--market-lookback-days", type=int, default=1)
    parser.add_argument("--news-lookback-days", type=int, default=30)
    parser.add_argument("--news-source", choices=("auto", "gdelt", "google_rss"), default="auto")
    parser.add_argument("--allow-wikipedia-fallback", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--no-rebuild", action="store_true")
    args = parser.parse_args()
    result, comparison, _manifest = run_live_metrics(
        target_events=args.target_events,
        max_event_pages=args.max_event_pages,
        market_lookback_days=args.market_lookback_days,
        news_lookback_days=args.news_lookback_days,
        news_source=args.news_source,
        allow_wikipedia_fallback=args.allow_wikipedia_fallback,
        refresh=args.refresh,
        rebuild=not args.no_rebuild,
    )
    events, news = load_live_corpus()
    stances = stance_distribution(events, news)
    print(
        result.resume_line()
        + f" brier_delta_posterior_market={comparison.posterior_minus_market:+.6f}"
        + f" brier_delta_blend_market={comparison.blend_minus_market:+.6f}"
        + f" posterior_ci=[{comparison.posterior_ci_low:+.6f},{comparison.posterior_ci_high:+.6f}]"
        + f" stances_yes={stances.get('yes', 0)}"
        + f" stances_no={stances.get('no', 0)}"
        + f" stances_neutral={stances.get('neutral', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
