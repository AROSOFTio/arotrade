"""Economic-calendar news feed (Forex Factory weekly JSON) + Gemini impact analysis.

The calendar fetch is cached for an hour; AI impact summaries are cached per
symbol for an hour. Synthetic indices are unaffected by macro news and return
an empty relevance set.
"""

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

CALENDAR_URLS = (
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
)

_calendar_cache: dict = {"expires": 0.0, "events": []}
_impact_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()

_CURRENCY_FOR_INDEX = {
    "US30": "USD", "US100": "USD", "US500": "USD",
    "GER40": "EUR", "FRA40": "EUR", "UK100": "GBP",
    "JPN225": "JPY", "AUS200": "AUD", "HK50": "CNY",
    "XAUUSD": "USD", "XAGUSD": "USD", "XPTUSD": "USD",
    "BTCUSD": "USD", "ETHUSD": "USD",
}

_SYNTHETICS = {"V10", "V25", "V50", "V75", "V100", "BOOM1000", "CRASH1000", "STEP"}


class NewsError(Exception):
    pass


def relevant_currencies(symbol: str) -> set[str]:
    symbol = symbol.upper()
    if symbol in _SYNTHETICS:
        return set()
    if symbol in _CURRENCY_FOR_INDEX:
        return {_CURRENCY_FOR_INDEX[symbol]}
    if len(symbol) == 6:  # forex pair
        return {symbol[:3], symbol[3:]}
    return set()


def _clean_event(event: dict) -> dict:
    return {
        "title": event.get("title", ""),
        "currency": event.get("country", ""),
        "date": event.get("date", ""),
        "impact": event.get("impact", ""),
        "forecast": event.get("forecast") or None,
        "previous": event.get("previous") or None,
    }


def fetch_calendar() -> list[dict]:
    now = time.monotonic()
    with _lock:
        if _calendar_cache["expires"] > now and _calendar_cache["events"]:
            return _calendar_cache["events"]

    errors = []
    cleaned = []
    seen = set()
    for url in CALENDAR_URLS:
        try:
            response = httpx.get(url, timeout=20.0, follow_redirects=True)
            response.raise_for_status()
            events = response.json()
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            continue

        for event in events:
            try:
                item = _clean_event(event)
                key = (item["title"], item["currency"], item["date"])
                if key in seen:
                    continue
                seen.add(key)
                cleaned.append(item)
            except Exception:
                continue

    if not cleaned:
        raise NewsError(f"Could not fetch the economic calendar: {'; '.join(errors) or 'no events returned'}")

    with _lock:
        _calendar_cache["events"] = cleaned
        _calendar_cache["expires"] = now + 3600.0
    return cleaned


def upcoming_events(symbol: Optional[str] = None, hours_ahead: int = 168, include_past_hours: int = 4) -> list[dict]:
    """High/medium-impact events in the window, optionally filtered for a symbol."""
    events = fetch_calendar()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=include_past_hours)
    window_end = now + timedelta(hours=hours_ahead)

    currencies = relevant_currencies(symbol) if symbol else None
    if currencies is not None and not currencies:
        return []  # synthetics: no macro exposure

    selected = []
    for event in events:
        if event["impact"] not in ("High", "Medium"):
            continue
        if currencies and event["currency"] not in currencies:
            continue
        try:
            event_time = datetime.fromisoformat(event["date"])
        except (ValueError, TypeError):
            continue
        if window_start <= event_time <= window_end:
            selected.append({**event, "date": event_time.isoformat()})

    selected.sort(key=lambda item: item["date"])
    return selected


def get_cached_impact(symbol: str) -> Optional[dict]:
    entry = _impact_cache.get(symbol.upper())
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def set_cached_impact(symbol: str, analysis: dict) -> None:
    _impact_cache[symbol.upper()] = (time.monotonic() + 3600.0, analysis)
