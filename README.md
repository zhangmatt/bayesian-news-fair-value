# Bayesian News Fair Value

Standalone research repo for a Bayesian fair-value estimator for binary
Polymarket/Kalshi-style event contracts.

The model starts with a market-implied Beta prior, ingests timestamped news,
classifies stance toward YES, converts weighted stance into a likelihood update,
and compares the posterior probability to the market price.

The evaluation standard is point-in-time replay. Market prices are sampled before
resolution, news is filtered by publish and observed timestamps, and no resolved
outcome text is used in the update.

## Layout
```text
src/fair_value_research/news  Bayesian updater, ingestion, stance, replay
data/news/fixtures            Tiny offline smoke-test corpus
data/news/live                50-contract historical corpus and news log
tests/news                    Unit and replay tests
metrics.md                    Reproducible point-in-time report
```

## Run
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
make test
make metrics
```

`make metrics` is offline by default and replays the committed 50-contract
Polymarket corpus. `make live-refresh` rebuilds from public read-only endpoints
and Google News RSS.

## Model
Each event is represented by an `EventContract` with question, resolution text,
close/resolve timestamps, market price, and outcome when resolved.

The Beta prior is centered on the point-in-time market-implied probability.
Aggregated YES/NO stance evidence becomes fractional pseudo-counts, and the
update strength knob controls how much text can move the posterior.

The default classifier is a transparent stance lexicon for deterministic replay.
An optional zero-shot NLI classifier is available through the `nlp` extra, but
the reported corpus below uses the deterministic classifier.

News items carry both `published_at` and `point_in_time_at`. Replay only scores
items available at the market forecast timestamp.

## Current Result
Corpus: 50 resolved Polymarket contracts, 448 Google News RSS headline/snippet
items, no Wikipedia fallback. Stances are yes `47`, no `5`, neutral `396`.

Market Brier is `0.005970`. Posterior Brier is `0.008387`. The 50/50
market-posterior blend Brier is `0.006932`.

Posterior-minus-market Brier delta is `+0.002417` with bootstrap CI
`[-0.000348, +0.007153]`. The posterior is worse than the market, and the
difference is within noise for this sample.

This is an honest null/negative result: the pipeline works, but this simple
news-stance likelihood mapping does not beat the market on the current corpus.

## Caveats
Google RSS `pubDate` is weaker than GDELT first-seen timestamps. The stance
classifier is intentionally simple. Larger resolved corpora, better entity
matching, and cross-validated update strength are the next research steps.
