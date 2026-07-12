from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from app.services import news


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class NewsFeedTests(unittest.TestCase):
    def setUp(self):
        news._calendar_cache["expires"] = 0.0
        news._calendar_cache["events"] = []

    def test_fetch_calendar_combines_this_week_and_next_week(self):
        def fake_get(url, **_kwargs):
            if "nextweek" in url:
                return FakeResponse([{"title": "NFP", "country": "USD", "date": "2026-07-17T12:30:00+00:00", "impact": "High"}])
            return FakeResponse([{"title": "CPI", "country": "USD", "date": "2026-07-14T12:30:00+00:00", "impact": "High"}])

        with patch("app.services.news.httpx.get", side_effect=fake_get):
            events = news.fetch_calendar()

        self.assertEqual([event["title"] for event in events], ["CPI", "NFP"])

    def test_upcoming_events_filters_symbol_currencies(self):
        now = datetime.now(timezone.utc)
        events = [
            {"title": "USD CPI", "currency": "USD", "date": (now + timedelta(days=3)).isoformat(), "impact": "High", "forecast": None, "previous": None},
            {"title": "EUR CPI", "currency": "EUR", "date": (now + timedelta(days=3)).isoformat(), "impact": "High", "forecast": None, "previous": None},
        ]

        with patch("app.services.news.fetch_calendar", return_value=events):
            selected = news.upcoming_events("XAUUSD")

        self.assertEqual([event["title"] for event in selected], ["USD CPI"])


if __name__ == "__main__":
    unittest.main()
