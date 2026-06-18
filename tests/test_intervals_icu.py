"""Tests for shared intervals.icu API helpers."""

from __future__ import annotations

from datetime import date

from intervalssync import intervals_icu


class FakeResponse:
    def __init__(self, *, status=200, json_data=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._json = json_data

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self.ok:
            raise intervals_icu.requests.HTTPError(f"HTTP {self.status_code}")


def test_fetch_calendar_workouts(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session,
        "get",
        lambda self, *a, **k: FakeResponse(
            json_data=[
                {
                    "id": 100,
                    "category": "WORKOUT",
                    "name": "Big Gear",
                    "description": "Strength",
                    "type": "Ride",
                    "workout_doc": {"steps": [{"duration": 120}]},
                },
                {
                    "id": 101,
                    "category": "NOTE",
                    "name": "Rest day",
                },
            ]
        ),
    )
    items = intervals_icu.fetch_calendar_workouts(
        "key", date(2026, 6, 1), date(2026, 6, 14)
    )
    assert len(items) == 1
    assert items[0].event_id == 100
    assert items[0].name == "Big Gear"


def test_fetch_sport_settings_max_hr(monkeypatch):
    captured: dict = {}

    def fake_get(self, url, auth, timeout):
        captured["url"] = url
        captured["auth"] = auth
        return FakeResponse(json_data={"max_hr": 193, "lthr": 176})

    monkeypatch.setattr(intervals_icu.requests.Session, "get", fake_get)
    assert intervals_icu.fetch_sport_settings_max_hr("api-key", "Ride") == 193.0
    assert captured["url"].endswith("/sport-settings/Ride")
    assert captured["auth"] == ("API_KEY", "api-key")
