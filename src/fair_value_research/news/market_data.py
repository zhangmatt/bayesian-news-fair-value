"""Market/event data clients and venue normalization."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fair_value_research.news.models import EventContract, normalize_probability, parse_dt
from fair_value_research.news.storage import read_json, read_jsonl, write_json

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_PATH = REPO_ROOT / "data" / "news" / "fixtures" / "markets.jsonl"
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "market_data"


def normalize_implied_probability(price: float | int | str) -> float:
    return normalize_probability(price, "price")


class DiskJsonCache:
    """Simple URL cache so read-only API calls can be replayed offline."""

    def __init__(self, cache_dir: str | Path = DEFAULT_CACHE_DIR, timeout: float = 15.0) -> None:
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout

    def _path_for(self, url: str, params: dict[str, Any] | None) -> Path:
        encoded = urllib.parse.urlencode(params or {}, doseq=True)
        digest = hashlib.sha256(f"{url}?{encoded}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def get_json(self, url: str, params: dict[str, Any] | None = None, refresh: bool = False) -> Any:
        cache_path = self._path_for(url, params)
        if cache_path.exists() and not refresh:
            return read_json(cache_path)
        query = urllib.parse.urlencode(params or {}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        request = urllib.request.Request(full_url, headers={"User-Agent": "bayesian-news/0.1"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        write_json(cache_path, payload)
        return payload


class FixtureMarketDataClient:
    """Offline market client backed by normalized JSONL fixtures."""

    def __init__(self, path: str | Path = DEFAULT_FIXTURE_PATH) -> None:
        self.path = Path(path)

    def load_contracts(self) -> list[EventContract]:
        return [EventContract.from_dict(row) for row in read_jsonl(self.path)]

    def get_contract(self, event_id: str) -> EventContract:
        for contract in self.load_contracts():
            if contract.event_id == event_id:
                return contract
        raise KeyError(f"fixture event not found: {event_id}")


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _maybe_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value)
    return default


def extract_polymarket_yes_probability(market: dict[str, Any]) -> float:
    """Extract a YES probability from common Gamma market payload shapes."""

    direct_fields = ("bestBid", "midpoint", "lastTradePrice", "lastPrice", "price")
    bid = _as_float(market.get("bestBid"))
    ask = _as_float(market.get("bestAsk"))
    if bid is not None and ask is not None and 0 <= bid <= ask:
        return normalize_implied_probability((bid + ask) / 2)

    for field in direct_fields:
        value = _as_float(market.get(field))
        if value is not None:
            return normalize_implied_probability(value)

    outcomes = [str(x).lower() for x in _maybe_json_list(market.get("outcomes"))]
    prices = _maybe_json_list(market.get("outcomePrices"))
    if prices:
        yes_index = outcomes.index("yes") if "yes" in outcomes else 0
        return normalize_implied_probability(prices[yes_index])

    raise ValueError(f"could not extract Polymarket YES price for market {market.get('id')}")


def polymarket_market_to_contract(
    market: dict[str, Any],
    event: dict[str, Any] | None = None,
    as_of: str | None = None,
) -> EventContract:
    event = event or {}
    event_id = _first_text(market.get("conditionId"), market.get("id"), market.get("slug"))
    question = _first_text(market.get("question"), market.get("title"), event.get("title"))
    close_time = parse_dt(_first_text(market.get("endDate"), event.get("endDate"), as_of))
    return EventContract(
        event_id=f"polymarket:{event_id}",
        venue="polymarket",
        ticker=_first_text(market.get("slug"), event_id),
        question=question,
        resolution_criteria=_first_text(
            market.get("resolutionCriteria"),
            market.get("description"),
            event.get("description"),
        ),
        close_time=close_time,
        resolve_time=parse_dt(market.get("resolvedTime") or event.get("resolvedTime")),
        as_of=parse_dt(as_of),
        current_price=extract_polymarket_yes_probability(market),
        keywords=tuple(filter(None, [question, event.get("title")])),
        metadata={"raw_market": market, "raw_event": event},
    )


class PolymarketGammaClient:
    """Read-only Gamma client for event/market discovery."""

    base_url = "https://gamma-api.polymarket.com"

    def __init__(self, cache: DiskJsonCache | None = None) -> None:
        self.cache = cache or DiskJsonCache()

    def fetch_event_by_slug(self, slug: str, refresh: bool = False) -> dict[str, Any] | list[Any]:
        return self.cache.get_json(f"{self.base_url}/events", {"slug": slug}, refresh=refresh)

    def fetch_active_events(self, limit: int = 100, offset: int = 0, refresh: bool = False) -> Any:
        params = {"active": "true", "closed": "false", "limit": limit, "offset": offset}
        return self.cache.get_json(f"{self.base_url}/events", params, refresh=refresh)

    def contracts_from_event_slug(self, slug: str, as_of: str | None = None) -> list[EventContract]:
        payload = self.fetch_event_by_slug(slug)
        event = payload[0] if isinstance(payload, list) and payload else payload
        markets = event.get("markets", []) if isinstance(event, dict) else []
        return [polymarket_market_to_contract(market, event, as_of=as_of) for market in markets]


class PolymarketClobClient:
    """Read-only Polymarket CLOB price helpers for known token IDs."""

    base_url = "https://clob.polymarket.com"

    def __init__(self, cache: DiskJsonCache | None = None) -> None:
        self.cache = cache or DiskJsonCache()

    def midpoint_probability(self, token_id: str, refresh: bool = False) -> float:
        payload = self.cache.get_json(
            f"{self.base_url}/midpoint",
            {"token_id": token_id},
            refresh=refresh,
        )
        value = payload.get("mid") if isinstance(payload, dict) else payload
        return normalize_implied_probability(value)

    def side_probability(self, token_id: str, side: str = "BUY", refresh: bool = False) -> float:
        payload = self.cache.get_json(
            f"{self.base_url}/price",
            {"token_id": token_id, "side": side.upper()},
            refresh=refresh,
        )
        value = payload.get("price") if isinstance(payload, dict) else payload
        return normalize_implied_probability(value)


def extract_kalshi_yes_probability(market: dict[str, Any]) -> float:
    """Extract a YES probability from Kalshi dollar or cent price fields."""

    yes_bid = _as_float(market.get("yes_bid_dollars") or market.get("yes_bid"))
    yes_ask = _as_float(market.get("yes_ask_dollars") or market.get("yes_ask"))
    if yes_bid is not None and yes_ask is not None and yes_bid <= yes_ask:
        return normalize_implied_probability((yes_bid + yes_ask) / 2)

    for field in ("last_price_dollars", "last_price", "previous_price_dollars"):
        value = _as_float(market.get(field))
        if value is not None:
            return normalize_implied_probability(value)

    raise ValueError(f"could not extract Kalshi YES price for market {market.get('ticker')}")


def kalshi_market_to_contract(market: dict[str, Any], as_of: str | None = None) -> EventContract:
    title = _first_text(market.get("title"), market.get("subtitle"), market.get("ticker"))
    criteria = "\n".join(
        part
        for part in (
            market.get("rules_primary"),
            market.get("rules_secondary"),
            market.get("settlement_value_dollars"),
        )
        if part
    )
    return EventContract(
        event_id=f"kalshi:{market.get('ticker')}",
        venue="kalshi",
        ticker=str(market.get("ticker")),
        question=title,
        resolution_criteria=criteria,
        close_time=parse_dt(market.get("close_time") or market.get("expiration_time")),
        resolve_time=parse_dt(market.get("settlement_ts") or market.get("expiration_time")),
        as_of=parse_dt(as_of or market.get("updated_time")),
        current_price=extract_kalshi_yes_probability(market),
        keywords=tuple(filter(None, [title, market.get("event_ticker")])),
        metadata={"raw_market": market},
    )


class KalshiClient:
    """Read-only Kalshi REST client for public market data."""

    base_url = "https://external-api.kalshi.com/trade-api/v2"

    def __init__(self, cache: DiskJsonCache | None = None) -> None:
        self.cache = cache or DiskJsonCache()

    def get_markets(
        self,
        status: str | None = "open",
        limit: int = 100,
        cursor: str | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        return self.cache.get_json(f"{self.base_url}/markets", params, refresh=refresh)

    def get_market(self, ticker: str, refresh: bool = False) -> dict[str, Any]:
        return self.cache.get_json(f"{self.base_url}/markets/{ticker}", refresh=refresh)

    def open_contracts(self, limit: int = 100) -> list[EventContract]:
        payload = self.get_markets(status="open", limit=limit)
        markets = payload.get("markets", []) if isinstance(payload, dict) else []
        return [kalshi_market_to_contract(market) for market in markets]
