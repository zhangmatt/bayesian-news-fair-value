"""Build a real point-in-time corpus from public market and news endpoints."""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import requests
import xml.etree.ElementTree as ET

from fair_value_research.news.models import EventContract, NewsItem, dt_to_iso, normalize_probability, parse_dt
from fair_value_research.news.storage import read_json, read_jsonl, write_json, write_jsonl

REPO_ROOT = Path(__file__).resolve().parents[3]
LIVE_DATA_DIR = REPO_ROOT / "data" / "news" / "live"
LIVE_MARKETS_PATH = LIVE_DATA_DIR / "markets.jsonl"
LIVE_NEWS_PATH = LIVE_DATA_DIR / "news.jsonl"
LIVE_MANIFEST_PATH = LIVE_DATA_DIR / "manifest.json"
LIVE_HTTP_CACHE = REPO_ROOT / ".cache" / "live_http"
POLYMARKET_EVENTS_URL = "https://gamma-api.polymarket.com/events"
POLYMARKET_PRICE_HISTORY_URL = "https://clob.polymarket.com/prices-history"
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
NOW_UTC = datetime(2026, 7, 10, tzinfo=timezone.utc)


@dataclass(frozen=True)
class CorpusBuildResult:
    events: list[EventContract]
    news: list[NewsItem]
    skipped: dict[str, int]
    manifest: dict[str, Any]


class CachedRequests:
    """Verified HTTP client with deterministic cache keys and polite sleeps."""

    def __init__(self, cache_dir: str | Path = LIVE_HTTP_CACHE, timeout: float = 12.0) -> None:
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self.disabled_hosts: set[str] = set()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "bayesian-news/0.1 research"})

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        refresh: bool = False,
        min_interval_seconds: float = 0.0,
        backoff_seconds: tuple[float, ...] = (6.0,),
    ) -> Any:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        host = urlparse(url).netloc
        if host in self.disabled_hosts:
            raise requests.HTTPError(f"{host} disabled after repeated live failures")
        cache_path = self._cache_path(url, params)
        if cache_path.exists() and not refresh:
            return read_json(cache_path)
        if min_interval_seconds > 0:
            time.sleep(min_interval_seconds)
        response = None
        for attempt, backoff in enumerate((0.0,) + backoff_seconds):
            if attempt > 0:
                time.sleep(max(backoff, min_interval_seconds))
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code != 429:
                break
        assert response is not None
        response.raise_for_status()
        payload = response.json()
        write_json(cache_path, payload)
        return payload

    def get_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        refresh: bool = False,
        min_interval_seconds: float = 0.0,
        backoff_seconds: tuple[float, ...] = (6.0,),
    ) -> str:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        host = urlparse(url).netloc
        if host in self.disabled_hosts:
            raise requests.HTTPError(f"{host} disabled after repeated live failures")
        cache_path = self._cache_path(url, params).with_suffix(".txt")
        if cache_path.exists() and not refresh:
            return cache_path.read_text(encoding="utf-8")
        if min_interval_seconds > 0:
            time.sleep(min_interval_seconds)
        response = None
        for attempt, backoff in enumerate((0.0,) + backoff_seconds):
            if attempt > 0:
                time.sleep(max(backoff, min_interval_seconds))
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code != 429:
                break
        assert response is not None
        response.raise_for_status()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(response.text, encoding="utf-8")
        return response.text

    def _cache_path(self, url: str, params: dict[str, Any]) -> Path:
        encoded = json.dumps({"url": url, "params": params}, sort_keys=True)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"


def build_live_corpus(
    target_events: int = 50,
    max_event_pages: int = 12,
    market_lookback_days: int = 1,
    news_lookback_days: int = 7,
    max_news_per_event: int = 12,
    news_source: str = "auto",
    allow_wikipedia_fallback: bool = False,
    refresh: bool = False,
    progress: bool = True,
) -> CorpusBuildResult:
    http = CachedRequests()
    selected_events: list[EventContract] = []
    selected_news: list[NewsItem] = []
    seen_ids: set[str] = set()
    skipped: dict[str, int] = {}

    for page in range(max_event_pages):
        if len(selected_events) >= target_events:
            break
        if progress:
            print(f"live_corpus page={page + 1} selected={len(selected_events)}", file=sys.stderr, flush=True)
        events_payload = http.get_json(
            POLYMARKET_EVENTS_URL,
            {
                "closed": "true",
                "limit": 100,
                "offset": page * 100,
                "order": "volume",
                "ascending": "false",
            },
            refresh=refresh,
        )
        for event_payload in events_payload:
            if len(selected_events) >= target_events:
                break
            if _event_has_excluded_tag(event_payload):
                _increment(skipped, "excluded_tag")
                continue
            for market_payload in event_payload.get("markets") or []:
                if len(selected_events) >= target_events:
                    break
                contract = _polymarket_contract_from_resolved_market(
                    event_payload,
                    market_payload,
                    http,
                    market_lookback_days=market_lookback_days,
                    refresh=refresh,
                )
                if contract is None:
                    _increment(skipped, "market_not_usable")
                    continue
                if contract.event_id in seen_ids:
                    _increment(skipped, "duplicate")
                    continue
                event_news, source_used = fetch_real_news_for_event(
                    contract,
                    http,
                    lookback_days=news_lookback_days,
                    max_records=max_news_per_event,
                    news_source=news_source,
                    refresh=refresh,
                )
                if not event_news and allow_wikipedia_fallback:
                    event_news = fetch_wikipedia_current_events_for_event(
                        contract,
                        http,
                        lookback_days=news_lookback_days,
                        max_records=max_news_per_event,
                        refresh=refresh,
                    )
                    source_used = "wikipedia_current_events"
                selected_events.append(contract)
                selected_news.extend(event_news)
                seen_ids.add(contract.event_id)
                if not event_news:
                    _increment(skipped, "no_news")
                _increment(skipped, f"source:{source_used}")
                if progress:
                    print(
                        f"selected {len(selected_events)}/{target_events}: "
                        f"{contract.ticker} news={len(event_news)} source={source_used} "
                        f"price={contract.implied_probability:.3f}",
                        file=sys.stderr,
                        flush=True,
                    )

    manifest = {
        "built_at": dt_to_iso(datetime.now(timezone.utc)),
        "source": source_description(news_source, allow_wikipedia_fallback),
        "target_events": target_events,
        "events_analyzed": len(selected_events),
        "news_items": len(selected_news),
        "market_lookback_days": market_lookback_days,
        "news_lookback_days": news_lookback_days,
        "news_source_requested": news_source,
        "allow_wikipedia_fallback": allow_wikipedia_fallback,
        "max_news_per_event": max_news_per_event,
        "skipped": skipped,
        "disabled_hosts": sorted(http.disabled_hosts),
        "no_lookahead_rule": (
            "GDELT uses seendate as first-seen point-in-time; Google News RSS fallback "
            "uses article pubDate as the observed timestamp and filters pubDate <= market as_of"
        ),
    }
    write_jsonl(LIVE_MARKETS_PATH, [event.to_dict() for event in selected_events])
    write_jsonl(LIVE_NEWS_PATH, [item.to_dict() for item in selected_news])
    write_json(LIVE_MANIFEST_PATH, manifest)
    return CorpusBuildResult(selected_events, selected_news, skipped, manifest)


def load_live_corpus() -> tuple[list[EventContract], list[NewsItem]]:
    events = [EventContract.from_dict(row) for row in read_jsonl(LIVE_MARKETS_PATH)]
    news = [NewsItem.from_dict(row) for row in read_jsonl(LIVE_NEWS_PATH)]
    return events, news


def source_description(news_source: str, allow_wikipedia_fallback: bool) -> str:
    if news_source == "google_rss":
        base = "Polymarket Gamma + Polymarket CLOB prices-history + Google News RSS"
    elif news_source == "gdelt":
        base = "Polymarket Gamma + Polymarket CLOB prices-history + GDELT DOC 2.0"
    else:
        base = "Polymarket Gamma + Polymarket CLOB prices-history + GDELT DOC 2.0 with Google News RSS fallback"
    if allow_wikipedia_fallback:
        return base + " and Wikipedia Current Events fallback"
    return base


def fetch_real_news_for_event(
    event: EventContract,
    http: CachedRequests,
    lookback_days: int,
    max_records: int,
    news_source: str,
    refresh: bool = False,
) -> tuple[list[NewsItem], str]:
    if news_source not in {"auto", "gdelt", "google_rss"}:
        raise ValueError("news_source must be auto, gdelt, or google_rss")
    if news_source in {"auto", "gdelt"} and "api.gdeltproject.org" not in http.disabled_hosts:
        gdelt_items = fetch_gdelt_news_for_event(event, http, lookback_days, max_records, refresh=refresh)
        if gdelt_items or news_source == "gdelt":
            return gdelt_items, "gdelt"
        http.disabled_hosts.add("api.gdeltproject.org")
    if news_source in {"auto", "google_rss"}:
        return (
            fetch_google_news_rss_for_event(event, http, lookback_days, max_records, refresh=refresh),
            "google_rss",
        )
    return [], "none"


def fetch_gdelt_news_for_event(
    event: EventContract,
    http: CachedRequests,
    lookback_days: int,
    max_records: int,
    refresh: bool = False,
) -> list[NewsItem]:
    as_of = event.as_of or event.close_time
    start = as_of - timedelta(days=lookback_days)
    query_terms = list(event.entities[:3] or event.keywords[:3])
    if not query_terms:
        query_terms = extract_query_terms(event.question, event.metadata.get("event_title", ""))
    if not query_terms:
        return []
    query = " OR ".join(f'"{term}"' if " " in term else term for term in query_terms[:3])
    payload = _fetch_gdelt_payload(
        http,
        query=f"({query}) sourcelang:English",
        start=start,
        as_of=as_of,
        max_records=max_records,
        refresh=refresh,
    )
    if not payload:
        return []

    items: list[NewsItem] = []
    seen_urls: set[str] = set()
    for article in payload.get("articles", []):
        url = article.get("url") or ""
        title = article.get("title") or ""
        if not title or url in seen_urls:
            continue
        seen_urls.add(url)
        seen = parse_gdelt_seen_date(article.get("seendate")) or as_of
        if seen > as_of:
            continue
        text = title
        matches = [term for term in event.event_terms if term and term.lower() in text.lower()]
        if not matches:
            matches = [term for term in query_terms if term.lower() in text.lower()]
        if not matches:
            continue
        # GDELT ArtList exposes article titles and first-seen timestamps, not
        # full text. We set both publication and point-in-time timestamps to the
        # GDELT seen time so replay cannot use articles unavailable at as_of.
        items.append(
            NewsItem(
                item_id=f"gdelt:{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}",
                event_id=event.event_id,
                source=article.get("domain") or "gdelt",
                title=title,
                body=article.get("sourcecountry") or "",
                published_at=seen,
                point_in_time_at=seen,
                url=url,
                matched_terms=tuple(dict.fromkeys(matches)),
                metadata={
                    "language": article.get("language"),
                    "gdelt_query": payload.get("_query"),
                    "gdelt_seendate": article.get("seendate"),
                },
            )
        )
    return sorted(items, key=lambda item: item.published_at)


def fetch_wikipedia_current_events_for_event(
    event: EventContract,
    http: CachedRequests,
    lookback_days: int,
    max_records: int,
    refresh: bool = False,
) -> list[NewsItem]:
    as_of = event.as_of or event.close_time
    start_date = (as_of - timedelta(days=lookback_days)).date()
    end_date = as_of.date()
    query_terms = list(event.entities[:4] or event.keywords[:4])
    items: list[NewsItem] = []
    day_count = (end_date - start_date).days + 1
    for offset in range(day_count):
        if len(items) >= max_records:
            break
        day = start_date + timedelta(days=offset)
        title = f"Portal:Current events/{day.year} {day.strftime('%B')} {day.day}"
        cutoff = min(as_of, datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
        params = {
            "action": "query",
            "format": "json",
            "prop": "revisions",
            "titles": title,
            "rvprop": "timestamp|content",
            "rvslots": "main",
            "rvlimit": 1,
            "rvdir": "older",
            "rvstart": dt_to_iso(cutoff),
        }
        try:
            payload = http.get_json(WIKIPEDIA_API_URL, params, refresh=refresh)
        except requests.RequestException:
            continue
        content, revision_ts = _extract_mediawiki_revision(payload)
        if not content or revision_ts is None or revision_ts > as_of:
            continue
        for line in _current_event_lines(content):
            if len(items) >= max_records:
                break
            clean = clean_wikitext(line)
            if not clean or not _line_relevant(clean, event, query_terms):
                continue
            items.append(
                NewsItem(
                    item_id=f"wiki:{hashlib.sha1((title + clean).encode('utf-8')).hexdigest()[:16]}",
                    event_id=event.event_id,
                    source="Wikipedia Current Events",
                    title=clean[:240],
                    body=title,
                    published_at=revision_ts,
                    point_in_time_at=revision_ts,
                    url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    matched_terms=tuple(_matched_query_tokens(clean, event, query_terms)),
                    metadata={"revision_timestamp": dt_to_iso(revision_ts), "page_title": title},
                )
            )
    return sorted(items, key=lambda item: item.published_at)


def _fetch_gdelt_payload(
    http: CachedRequests,
    query: str,
    start: datetime,
    as_of: datetime,
    max_records: int,
    refresh: bool,
) -> dict[str, Any] | None:
    params = {
        "query": query,
        "format": "json",
        "mode": "ArtList",
        "maxrecords": max_records,
        "sort": "DateDesc",
        "startdatetime": gdelt_timestamp(start),
        "enddatetime": gdelt_timestamp(as_of),
    }
    try:
        payload = http.get_json(
            GDELT_DOC_URL,
            params,
            refresh=refresh,
            min_interval_seconds=8.0,
            backoff_seconds=(15.0, 45.0, 90.0),
        )
    except requests.RequestException:
        return None
    if not payload.get("articles"):
        return None
    payload["_query"] = params["query"]
    return payload


def fetch_google_news_rss_for_event(
    event: EventContract,
    http: CachedRequests,
    lookback_days: int,
    max_records: int,
    refresh: bool = False,
) -> list[NewsItem]:
    as_of = event.as_of or event.close_time
    start = as_of - timedelta(days=lookback_days)
    query = google_news_query(event)
    params = {
        "q": f"{query} after:{start.date().isoformat()} before:{as_of.date().isoformat()}",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    try:
        xml_text = http.get_text(
            GOOGLE_NEWS_RSS_URL,
            params,
            refresh=refresh,
            min_interval_seconds=1.0,
            backoff_seconds=(5.0, 15.0, 30.0),
        )
    except requests.RequestException:
        return []
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []
    seen_links: set[str] = set()
    for node in root.findall(".//item"):
        if len(items) >= max_records:
            break
        raw_title = _xml_text(node, "title")
        link = _xml_text(node, "link")
        published = parse_rss_date(_xml_text(node, "pubDate")) or as_of
        if published > as_of or published < start or link in seen_links:
            continue
        seen_links.add(link)
        title, source = split_google_news_title(raw_title)
        description = clean_html(_xml_text(node, "description"))
        text = f"{title} {description}"
        if not _line_relevant(text, event, list(event.entities or event.keywords)):
            continue
        items.append(
            NewsItem(
                item_id=f"google:{hashlib.sha1(link.encode('utf-8')).hexdigest()[:16]}",
                event_id=event.event_id,
                source=source or "Google News RSS",
                title=title[:300],
                body=description[:1200],
                published_at=published,
                point_in_time_at=published,
                url=link,
                matched_terms=tuple(_matched_query_tokens(text, event, list(event.entities or event.keywords))),
                metadata={
                    "google_query": params["q"],
                    "source_feed": "Google News RSS",
                    "point_in_time_note": "RSS pubDate used as observed timestamp",
                },
            )
        )
    return sorted(items, key=lambda item: item.published_at)


def google_news_query(event: EventContract) -> str:
    question = event.question
    event_title = str(event.metadata.get("event_title") or "")
    query_terms = extract_query_terms(question, event_title)
    if "fed decision" in event_title.lower() or "interest rates" in question.lower():
        return '"Federal Reserve" OR FOMC OR "interest rates"'
    if "fed chair" in event_title.lower() or "fed chair" in question.lower():
        subject = _subject_after_will(question)
        if subject:
            return f'"{subject}" "Fed Chair"'
        return '"Fed Chair" "Federal Reserve"'
    if "popular vote" in question.lower() or "presidential election" in question.lower():
        subject = _subject_after_will(question)
        if subject and not subject.startswith("any other"):
            return f'"{subject}" "2024 election"'
        return '"2024 election" "popular vote"'
    if query_terms:
        term = query_terms[0]
        return f'"{term}"' if " " in term else term
    return f'"{event.ticker}"'


def _xml_text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    return "" if found is None or found.text is None else found.text.strip()


def parse_rss_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return parse_dt(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def split_google_news_title(raw_title: str) -> tuple[str, str]:
    if " - " not in raw_title:
        return raw_title.strip(), "Google News RSS"
    title, source = raw_title.rsplit(" - ", 1)
    return title.strip(), source.strip()


def clean_html(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_mediawiki_revision(payload: dict[str, Any]) -> tuple[str, datetime | None]:
    pages = payload.get("query", {}).get("pages", {})
    for page in pages.values():
        revisions = page.get("revisions") or []
        if not revisions:
            continue
        revision = revisions[0]
        content = revision.get("slots", {}).get("main", {}).get("*", "")
        return content, parse_dt(revision.get("timestamp"))
    return "", None


def _current_event_lines(content: str) -> list[str]:
    lines = []
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("*") and not stripped.startswith("<!--"):
            lines.append(stripped.lstrip("*").strip())
    return lines


def clean_wikitext(value: str) -> str:
    text = re.sub(r"\[https?://[^\s\]]+\s*([^\]]*)\]", r"\1", value)
    text = re.sub(r"\[\[[^|\]]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -*")


def _line_relevant(line: str, event: EventContract, query_terms: list[str]) -> bool:
    lowered = line.lower()
    for term in query_terms + list(event.keywords) + list(event.entities):
        if term and term.lower() in lowered:
            return True
    tokens = set(_significant_tokens(event.question + " " + " ".join(query_terms)))
    line_tokens = set(_significant_tokens(line))
    return len(tokens & line_tokens) >= 2


def _matched_query_tokens(line: str, event: EventContract, query_terms: list[str]) -> list[str]:
    lowered = line.lower()
    matches = [term for term in query_terms + list(event.keywords) + list(event.entities) if term and term.lower() in lowered]
    if matches:
        return list(dict.fromkeys(matches))
    tokens = sorted(set(_significant_tokens(event.question)) & set(_significant_tokens(line)))
    return tokens[:5]


def _significant_tokens(text: str) -> list[str]:
    stop_words = STOP_WORDS - {"election", "elections", "winner"}
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text)
        if token.lower() not in stop_words
    ]


def _polymarket_contract_from_resolved_market(
    event_payload: dict[str, Any],
    market_payload: dict[str, Any],
    http: CachedRequests,
    market_lookback_days: int,
    refresh: bool,
) -> EventContract | None:
    if not _is_binary_yes_no(market_payload):
        return None
    outcome = _polymarket_final_outcome(market_payload)
    if outcome is None:
        return None
    close_time = parse_dt(market_payload.get("closedTime") or event_payload.get("closedTime") or market_payload.get("endDate"))
    start_time = parse_dt(
        market_payload.get("startDate")
        or market_payload.get("createdAt")
        or event_payload.get("startDate")
        or event_payload.get("creationDate")
    )
    if close_time is None or close_time > NOW_UTC:
        return None
    clob_tokens = _json_list(market_payload.get("clobTokenIds"))
    if not clob_tokens:
        return None
    intended_as_of = choose_forecast_time(start_time, close_time, market_lookback_days)
    price_point = fetch_polymarket_price_at(
        str(clob_tokens[0]),
        intended_as_of,
        start_time=start_time,
        http=http,
        refresh=refresh,
    )
    if price_point is None:
        return None
    price_as_of, price = price_point
    query_terms = extract_query_terms(market_payload.get("question", ""), event_payload.get("title", ""))
    question = str(market_payload.get("question") or event_payload.get("title") or market_payload.get("slug"))
    market_id = str(market_payload.get("conditionId") or market_payload.get("id"))
    return EventContract(
        event_id=f"polymarket:{market_id}",
        venue="polymarket",
        ticker=str(market_payload.get("slug") or market_id),
        question=question,
        resolution_criteria=str(market_payload.get("description") or event_payload.get("description") or ""),
        close_time=close_time,
        resolve_time=parse_dt(event_payload.get("closedTime") or market_payload.get("closedTime")),
        as_of=price_as_of,
        current_price=price,
        implied_probability=price,
        outcome=outcome,
        keywords=tuple(dict.fromkeys(query_terms + [str(event_payload.get("title") or "")])),
        entities=tuple(query_terms[:4]),
        yes_terms=tuple(_yes_terms(question)),
        no_terms=tuple(_no_terms(question)),
        metadata={
            "event_id": event_payload.get("id"),
            "event_title": event_payload.get("title"),
            "market_id": market_payload.get("id"),
            "condition_id": market_payload.get("conditionId"),
            "clob_yes_token_id": str(clob_tokens[0]),
            "forecast_rule": f"latest CLOB history point at or before close_time - {market_lookback_days}d",
            "final_outcome_prices": market_payload.get("outcomePrices"),
            "volume": market_payload.get("volume") or market_payload.get("volumeNum"),
        },
    )


def fetch_polymarket_price_at(
    yes_token_id: str,
    as_of: datetime,
    start_time: datetime | None,
    http: CachedRequests,
    refresh: bool = False,
) -> tuple[datetime, float] | None:
    usable: list[dict[str, Any]] = []
    windows = [
        (max_dt(start_time, as_of - timedelta(days=2)) or (as_of - timedelta(days=2)), 60),
        (max_dt(start_time, as_of - timedelta(days=30)) or (as_of - timedelta(days=30)), 1440),
    ]
    for start, fidelity in windows:
        params = {
            "market": yes_token_id,
            "startTs": int(start.timestamp()),
            "endTs": int(as_of.timestamp()),
            "fidelity": fidelity,
        }
        try:
            payload = http.get_json(POLYMARKET_PRICE_HISTORY_URL, params, refresh=refresh)
        except requests.RequestException:
            continue
        history = payload.get("history") or []
        usable = [point for point in history if point.get("p") is not None and point.get("t") is not None]
        if usable:
            break
    if not usable:
        return None
    last = max(usable, key=lambda point: point["t"])
    price = normalize_probability(float(last["p"]), "historical_price")
    if math.isclose(price, 0.0) or math.isclose(price, 1.0):
        return None
    return datetime.fromtimestamp(int(last["t"]), tz=timezone.utc), price


def choose_forecast_time(
    start_time: datetime | None,
    close_time: datetime,
    market_lookback_days: int,
) -> datetime:
    candidate = close_time - timedelta(days=market_lookback_days)
    if start_time is None:
        return candidate
    minimum = start_time + timedelta(hours=6)
    if candidate <= minimum:
        return start_time + (close_time - start_time) / 2
    return candidate


def extract_query_terms(question: str, event_title: str) -> list[str]:
    text = f"{question} {event_title}"
    phrases = []
    for match in re.finditer(r"\b[A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,4}", text):
        phrase = re.sub(r"^Will\s+", "", match.group(0).strip(" ?"))
        if len(phrase) >= 3 and phrase.lower() not in STOP_PHRASES:
            phrases.append(phrase)
    if phrases:
        return list(dict.fromkeys(phrases))[:5]
    tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text)
        if token.lower() not in STOP_WORDS
    ]
    return list(dict.fromkeys(tokens))[:5]


def gdelt_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")


def parse_gdelt_seen_date(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return parse_dt(cleaned)


def _is_binary_yes_no(market_payload: dict[str, Any]) -> bool:
    outcomes = [str(item).lower() for item in _json_list(market_payload.get("outcomes"))]
    return len(outcomes) == 2 and outcomes[0] == "yes" and outcomes[1] == "no"


def _polymarket_final_outcome(market_payload: dict[str, Any]) -> int | None:
    prices = _json_list(market_payload.get("outcomePrices"))
    if len(prices) < 2:
        return None
    yes_price = float(prices[0])
    no_price = float(prices[1])
    if yes_price > 0.95 and no_price < 0.05:
        return 1
    if no_price > 0.95 and yes_price < 0.05:
        return 0
    return None


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _yes_terms(question: str) -> list[str]:
    terms = [
        "wins",
        "won",
        "victory",
        "approved",
        "passes",
        "confirmed",
        "above forecast",
        "likely",
    ]
    subject = _subject_after_will(question)
    if subject:
        terms.extend([f"{subject} wins", f"{subject} won", f"{subject} victory", f"{subject} leads"])
    return terms


def _no_terms(question: str) -> list[str]:
    terms = [
        "loses",
        "lost",
        "defeat",
        "rejected",
        "fails",
        "blocked",
        "below forecast",
        "unlikely",
    ]
    subject = _subject_after_will(question)
    if subject:
        terms.extend([f"{subject} loses", f"{subject} lost", f"{subject} defeat"])
    return terms


def _subject_after_will(question: str) -> str | None:
    match = re.search(r"\bWill\s+(.+?)\s+(win|beat|be|have|get|receive|become|take)\b", question)
    if not match:
        return None
    subject = re.sub(r"\s+", " ", match.group(1)).strip(" ?")
    return subject.lower() if 2 <= len(subject) <= 80 else None


def max_dt(a: datetime | None, b: datetime | None) -> datetime | None:
    values = [value for value in (a, b) if value is not None]
    return max(values) if values else None


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _event_has_excluded_tag(event_payload: dict[str, Any]) -> bool:
    text_parts = [str(event_payload.get("title") or "")]
    for tag in event_payload.get("tags") or []:
        if isinstance(tag, dict):
            text_parts.extend(str(tag.get(key) or "") for key in ("label", "slug", "name"))
        else:
            text_parts.append(str(tag))
    text = " ".join(text_parts).lower()
    return any(keyword in text for keyword in EXCLUDED_TAG_KEYWORDS)


EXCLUDED_TAG_KEYWORDS = {
    "sports",
    "nba",
    "nfl",
    "nhl",
    "mlb",
    "soccer",
    "basketball",
    "football",
    "hockey",
    "baseball",
    "champions league",
    "premier league",
    "super bowl",
    "big game",
}


STOP_WORDS = {
    "will",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "have",
    "has",
    "more",
    "less",
    "than",
    "over",
    "under",
    "before",
    "after",
    "what",
    "when",
    "who",
    "which",
    "win",
    "wins",
    "beat",
    "become",
}
STOP_PHRASES = {"will", "yes", "no", "all", "old"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a live Polymarket/GDELT corpus.")
    parser.add_argument("--target-events", type=int, default=50)
    parser.add_argument("--max-event-pages", type=int, default=12)
    parser.add_argument("--market-lookback-days", type=int, default=1)
    parser.add_argument("--news-lookback-days", type=int, default=30)
    parser.add_argument("--news-source", choices=("auto", "gdelt", "google_rss"), default="auto")
    parser.add_argument("--allow-wikipedia-fallback", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    result = build_live_corpus(
        target_events=args.target_events,
        max_event_pages=args.max_event_pages,
        market_lookback_days=args.market_lookback_days,
        news_lookback_days=args.news_lookback_days,
        news_source=args.news_source,
        allow_wikipedia_fallback=args.allow_wikipedia_fallback,
        refresh=args.refresh,
    )
    print(
        "LIVE_CORPUS "
        f"events={len(result.events)} "
        f"news_items={len(result.news)} "
        f"skipped={json.dumps(result.skipped, sort_keys=True)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
