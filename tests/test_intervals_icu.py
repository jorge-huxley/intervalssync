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


def test_legacy_sport_settings_preserve_fractional_thresholds(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session, "get",
        lambda *a, **k: FakeResponse(json_data={"ftp": 250.5, "lthr": 170.5}),
    )
    settings = intervals_icu.fetch_sport_settings("synthetic", "Ride")
    assert settings.ftp == 250.5
    assert settings.lthr == 170.5


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
                    "start_date_local": "2026-06-03T00:00:00",
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
    # Bryton schedules workouts by date; without this they never reach the
    # head unit. See build_workout_info().
    assert items[0].start_date == "2026-06-03"


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


def test_fetch_sport_settings(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session,
        "get",
        lambda self, *a, **k: FakeResponse(
            json_data={
                "ftp": 242,
                "lthr": 176,
                "max_hr": 193,
                "power_zones": [55, 75, 90, 105, 120, 999],
                "hr_zones": [120, 146, 166, 185, 193],
                "power_zone_names": [
                    "Active Recovery",
                    "Endurance",
                    "Tempo",
                    "Threshold",
                    "VO2 Max",
                    "Anaerobic",
                    "Neuromuscular",
                ],
                "hr_zone_names": [
                    "Recovery",
                    "Aerobic",
                    "Tempo",
                    "SubThreshold",
                    "SuperThreshold",
                    "Aerobic Capacity",
                    "Anaerobic",
                ],
            }
        ),
    )
    settings = intervals_icu.fetch_sport_settings("api-key", "Ride", strict=True)
    assert settings.ftp == 242.0
    assert settings.lthr == 176.0
    assert settings.max_hr == 193.0
    assert settings.power_zones == [55.0, 75.0, 90.0, 105.0, 120.0, 999.0]
    assert settings.hr_zones == [120.0, 146.0, 166.0, 185.0, 193.0]
    assert settings.power_zone_names[-1] == "Neuromuscular"
    assert settings.hr_zone_names[3] == "SubThreshold"
    assert settings.invalid_fields == frozenset()


def test_fetch_sport_settings_tracks_malformed_non_null_fields(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session,
        "get",
        lambda self, *a, **k: FakeResponse(
            json_data={
                "ftp": "not-a-number",
                "lthr": None,
                "max_hr": 193,
                "power_zones": [55, "bad", 999],
                "hr_zones": None,
                "power_zone_names": "not-a-list",
                "hr_zone_names": None,
            }
        ),
    )

    settings = intervals_icu.fetch_sport_settings("api-key", "Ride", strict=True)

    assert settings.ftp is None
    assert settings.lthr is None
    assert settings.hr_zones == []
    assert settings.invalid_fields == frozenset(
        {"ftp", "power_zones", "power_zone_names"}
    )


def test_fetch_sport_settings_preserves_fractional_thresholds_for_legacy_rounding(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session,
        "get",
        lambda self, *a, **k: FakeResponse(
            json_data={"ftp": 242.5, "lthr": 175.5, "max_hr": 192.5}
        ),
    )

    settings = intervals_icu.fetch_sport_settings("api-key", "Ride", strict=True)

    assert settings.ftp == 242.5
    assert settings.lthr == 175.5
    assert settings.max_hr == 192.5


def test_fetch_athlete_settings_normalizes_all_supported_profile_fields(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session,
        "get",
        lambda self, *a, **k: FakeResponse(
            json_data={
                "icu_resting_hr": 45,
                "icu_weight": 71.26,
                "weight": 99,
                "height": 1.725,
                "icu_date_of_birth": "1992-08-08",
                "sex": "male",
            }
        ),
    )

    settings = intervals_icu.fetch_athlete_settings("api-key")

    assert settings.resting_hr == 45
    assert settings.weight == 71.26
    assert settings.height_cm == 173
    assert settings.birth_date == "1992-08-08"
    assert settings.sex == 1
    assert settings.invalid_fields == frozenset()


def test_fetch_athlete_settings_falls_back_to_weight_and_maps_female(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session,
        "get",
        lambda self, *a, **k: FakeResponse(
            json_data={"icu_weight": None, "weight": 72.5, "sex": "FEMALE"}
        ),
    )

    settings = intervals_icu.fetch_athlete_settings("api-key")

    assert settings.weight == 72.5
    assert settings.sex == 2


def test_fetch_athlete_settings_distinguishes_missing_from_malformed(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session,
        "get",
        lambda self, *a, **k: FakeResponse(
            json_data={
                "icu_resting_hr": "bad",
                "icu_weight": -1,
                "height": 172,
                "icu_date_of_birth": "not-a-date",
                "sex": "unknown",
            }
        ),
    )

    settings = intervals_icu.fetch_athlete_settings("api-key")

    assert settings.resting_hr is None
    assert settings.weight is None
    assert settings.height_cm is None
    assert settings.birth_date is None
    assert settings.sex is None
    assert settings.invalid_fields == frozenset(
        {"resting_hr", "weight", "height", "birth_date", "sex"}
    )


def test_fetch_athlete_settings_keeps_absent_and_null_fields_missing(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session,
        "get",
        lambda self, *a, **k: FakeResponse(
            json_data={"icu_resting_hr": None, "height": None}
        ),
    )

    settings = intervals_icu.fetch_athlete_settings("api-key")

    assert settings.resting_hr is None
    assert settings.weight is None
    assert settings.height_cm is None
    assert settings.birth_date is None
    assert settings.sex is None
    assert settings.invalid_fields == frozenset()


def test_fetch_athlete_weight_prefers_icu_weight(monkeypatch):
    captured: dict = {}

    def fake_get(self, url, auth, timeout):
        captured["url"] = url
        captured["auth"] = auth
        return FakeResponse(json_data={"icu_weight": 76.1, "weight": 70.0})

    monkeypatch.setattr(intervals_icu.requests.Session, "get", fake_get)
    assert intervals_icu.fetch_athlete_weight("api-key") == 76.1
    assert captured["url"].endswith("/athlete/0")
    assert captured["auth"] == ("API_KEY", "api-key")


def test_fetch_athlete_weight_falls_back_to_weight(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session,
        "get",
        lambda self, *a, **k: FakeResponse(json_data={"weight": 72.5}),
    )
    assert intervals_icu.fetch_athlete_weight("api-key") == 72.5


def test_fetch_athlete_weight_missing(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests.Session,
        "get",
        lambda self, *a, **k: FakeResponse(json_data={"name": "Athlete"}),
    )
    assert intervals_icu.fetch_athlete_weight("api-key") is None
