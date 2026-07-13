"""News and social text ingestion with point-in-time replay support."""

from __future__ import annotations

import email.utils
import hashlib
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from fair_value_research.news.models import EventContract, NewsItem, parse_dt
from fair_value_research.news.storage import append_jsonl, read_jsonl, write_jsonl

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_NEWS_FIXTURE_PATH = REPO_ROOT / "data" / "news" / "fixtures" / "news.jsonl"
DEFAULT_NEWS_LOG_PATH = REPO_ROOT / ".cache" / "news_log.jsonl"


class NewsClient(Protocol):
    def fetch(self, event: EventContract, as_of: datetime) -> list[NewsItem]:
        ...


def stable_item_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def matched_terms(text: str, event: EventContract) -> tuple[str, ...]:
    lowered = text.lower()
    matches = [term for term in event.event_terms if term and term.lower() in lowered]
    return tuple(dict.fromkeys(matches))


def item_matches_event(item: NewsItem, event: EventContract, min_terms: int = 1) -> bool:
    if item.event_id == event.event_id:
        return True
    return len(matched_terms(item.text, event)) >= min_terms


class PointInTimeNewsLog:
    """Append-only news log filtered by publish time and observed ingestion time."""

    def __init__(self, path: str | Path = DEFAULT_NEWS_LOG_PATH) -> None:
        self.path = Path(path)

    def append(self, items: list[NewsItem]) -> None:
        existing_ids = {row["item_id"] for row in read_jsonl(self.path)}
        new_rows = [item.to_dict() for item in items if item.item_id not in existing_ids]
        append_jsonl(self.path, new_rows)

    def load(self, event: EventContract, as_of: datetime) -> list[NewsItem]:
        observed: list[NewsItem] = []
        for row in read_jsonl(self.path):
            item = NewsItem.from_dict(row)
            if item.published_at <= as_of and item.point_in_time_at <= as_of and item_matches_event(item, event):
                observed.append(item)
        return sorted(observed, key=lambda item: item.published_at)

    def replace(self, items: list[NewsItem]) -> None:
        write_jsonl(self.path, [item.to_dict() for item in items])


class FixtureNewsClient:
    """Offline news client backed by timestamped JSONL fixtures."""

    def __init__(self, path: str | Path = DEFAULT_NEWS_FIXTURE_PATH) -> None:
        self.path = Path(path)

    def load_all(self) -> list[NewsItem]:
        return [NewsItem.from_dict(row) for row in read_jsonl(self.path)]

    def fetch(self, event: EventContract, as_of: datetime) -> list[NewsItem]:
        items = []
        for item in self.load_all():
            if item.published_at > as_of or item.point_in_time_at > as_of:
                continue
            if item_matches_event(item, event):
                terms = matched_terms(item.text, event)
                items.append(
                    NewsItem(
                        item_id=item.item_id,
                        event_id=item.event_id,
                        source=item.source,
                        title=item.title,
                        body=item.body,
                        published_at=item.published_at,
                        point_in_time_at=item.point_in_time_at,
                        url=item.url,
                        matched_terms=terms or item.matched_terms,
                        metadata=item.metadata,
                    )
                )
        return sorted(items, key=lambda item: item.published_at)


class RssNewsClient:
    """Minimal RSS/Atom reader for free public feeds."""

    def __init__(self, feed_urls: list[str], timeout: float = 15.0) -> None:
        self.feed_urls = feed_urls
        self.timeout = timeout

    def fetch(self, event: EventContract, as_of: datetime) -> list[NewsItem]:
        items: list[NewsItem] = []
        for url in self.feed_urls:
            request = urllib.request.Request(url, headers={"User-Agent": "bayesian-news/0.1"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                root = ET.fromstring(response.read())
            for node in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                title = _xml_text(node, "title")
                body = _xml_text(node, "description") or _xml_text(node, "summary")
                published = _parse_feed_time(_xml_text(node, "pubDate") or _xml_text(node, "published")) or as_of
                link = _xml_text(node, "link")
                item = NewsItem(
                    item_id=stable_item_id(url, title, str(published)),
                    event_id=None,
                    source=urllib.parse.urlparse(url).netloc,
                    title=title,
                    body=body,
                    published_at=published,
                    point_in_time_at=as_of,
                    url=link,
                    matched_terms=matched_terms(f"{title} {body}", event),
                )
                if item.published_at <= as_of and item_matches_event(item, event):
                    items.append(item)
        return sorted(items, key=lambda item: item.published_at)


class GdeltDocClient:
    """Free GDELT DOC 2.0 reader for keyword-based article discovery."""

    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, max_records: int = 25, timeout: float = 15.0) -> None:
        self.max_records = max_records
        self.timeout = timeout

    def fetch(self, event: EventContract, as_of: datetime) -> list[NewsItem]:
        query_terms = event.keywords or event.entities or (event.question,)
        params = {
            "query": " OR ".join(f'"{term}"' for term in query_terms[:5]),
            "format": "json",
            "mode": "ArtList",
            "maxrecords": self.max_records,
            "sort": "DateDesc",
        }
        url = f"{self.endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": "bayesian-news/0.1"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        items = []
        for article in payload.get("articles", []):
            published = parse_dt(article.get("seendate")) or as_of
            title = article.get("title", "")
            body = article.get("sourcecountry", "")
            item = NewsItem(
                item_id=stable_item_id(article.get("url", ""), title, str(published)),
                event_id=None,
                source=article.get("domain", "gdelt"),
                title=title,
                body=body,
                published_at=published,
                point_in_time_at=as_of,
                url=article.get("url"),
                matched_terms=matched_terms(title, event),
                metadata={"language": article.get("language")},
            )
            if item.published_at <= as_of and item_matches_event(item, event):
                items.append(item)
        return sorted(items, key=lambda item: item.published_at)


class NewsIngestor:
    """Fetch through a client and persist the observed items before scoring."""

    def __init__(self, client: NewsClient, log: PointInTimeNewsLog | None = None) -> None:
        self.client = client
        self.log = log or PointInTimeNewsLog()

    def fetch_and_record(self, event: EventContract, as_of: datetime) -> list[NewsItem]:
        items = self.client.fetch(event, as_of)
        self.log.append(items)
        return items


def _xml_text(node: ET.Element, tag: str) -> str:
    found = node.find(tag)
    if found is None:
        found = node.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    return "" if found is None or found.text is None else found.text.strip()


def _parse_feed_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return parse_dt(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
