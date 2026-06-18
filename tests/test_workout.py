"""Tests for intervals.icu → iGPSPORT workout upload."""

from __future__ import annotations

from datetime import date

import pytest

from intervalssync import intervals_icu
from intervalssync.igpsport import workout


class FakeResponse:
    def __init__(self, *, status=200, json_data=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._json = json_data

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self.ok:
            raise workout.requests.HTTPError(f"HTTP {self.status_code}")


def test_icu_workout_doc_maps_simple_ftp_step():
    doc = {
        "duration": 3600,
        "steps": [
            {
                "duration": 3600,
                "power": {"value": 100, "units": "%ftp"},
            }
        ],
    }
    body = workout.icu_workout_doc_to_igps("FTP Test", "desc", doc)
    assert body is not None
    data = body["data"]
    assert data["title"] == "FTP Test"
    assert data["workoutType"] == "bike"
    assert data["sportBigType"] == 1
    assert data["totalTime"] == 3600
    step = data["structure"][0]
    assert step["type"] == "Step"
    assert step["length"] == {"unit": "Second", "value": 3600}
    assert step["intensityTarget"] == {
        "unit": "PercentOfFTP",
        "minValue": 100,
        "maxValue": 100,
    }


def test_icu_workout_doc_prefers_resolved_power_watts():
    doc = {
        "steps": [
            {
                "duration": 600,
                "warmup": True,
                "ramp": True,
                "power": {"start": 35, "end": 55, "units": "%ftp"},
                "_power": {"start": 98, "end": 154},
            }
        ],
    }
    body = workout.icu_workout_doc_to_igps("Warmup", "", doc)
    assert body is not None
    step = body["data"]["structure"][0]
    assert step["intensityClass"] == "WarmUp"
    assert step["intensityTarget"] == {
        "unit": "PowerCustom",
        "value": 0,
        "minValue": 98,
        "maxValue": 154,
    }


def test_icu_workout_doc_maps_repetition_block():
    doc = {
        "steps": [
            {
                "reps": 4,
                "steps": [
                    {"duration": 300, "power": {"value": 110, "units": "%ftp"}},
                    {"duration": 90, "power": {"value": 55, "units": "%ftp"}},
                ],
            }
        ],
    }
    body = workout.icu_workout_doc_to_igps("Intervals", "", doc)
    assert body is not None
    rep = body["data"]["structure"][0]
    assert rep["type"] == "Repetition"
    assert rep["length"] == {"unit": "Repetition", "value": 4}
    assert len(rep["steps"]) == 2


def test_icu_workout_doc_open_duration_step():
    doc = {
        "steps": [
            {
                "until_lap_press": True,
                "intensity": "rest",
            }
        ],
    }
    body = workout.icu_workout_doc_to_igps("Open", "", doc)
    assert body is not None
    step = body["data"]["structure"][0]
    assert step["openDuration"] == "true"
    assert step["intensityClass"] == "Rest"
    assert "length" not in step


def test_icu_workout_doc_returns_none_without_steps():
    assert workout.icu_workout_doc_to_igps("Empty", "", {}) is None
    assert workout.icu_workout_doc_to_igps("Empty", "", {"steps": []}) is None


def test_icu_workout_doc_includes_existing_id_for_update():
    doc = {"steps": [{"duration": 60}]}
    body = workout.icu_workout_doc_to_igps("Update", "", doc, existing_workout_id=5012)
    assert body is not None
    assert body["data"]["id"] == "5012"


def test_upload_custom_workout_returns_id(monkeypatch):
    monkeypatch.setattr(
        workout.requests.Session,
        "post",
        lambda self, *a, **k: FakeResponse(json_data={"code": 0, "data": {"workoutId": 999}}),
    )
    session = workout.requests.Session()
    wid = workout.upload_custom_workout(session, {"Authorization": "Bearer x"}, {"data": {}})
    assert wid == 999


def test_upload_custom_workout_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(
        workout.requests.Session,
        "post",
        lambda self, *a, **k: FakeResponse(status=400, json_data={"code": 1}),
    )
    session = workout.requests.Session()
    assert workout.upload_custom_workout(session, {}, {}) is None


def test_list_custom_workouts(monkeypatch):
    captured: dict = {}

    def fake_get(self, url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        return FakeResponse(json_data={"code": 0, "data": {"items": []}})

    monkeypatch.setattr(workout.requests.Session, "get", fake_get)
    session = workout.requests.Session()
    workout.list_custom_workouts(session, {"Authorization": "Bearer t"}, page_index=2, page_size=5)
    assert captured["url"] == workout.IGPS_WORKOUT_LIST_URL
    assert captured["params"] == {"PageIndex": 2, "PageSize": 5}


def test_fetch_all_custom_workout_ids_paginates(monkeypatch):
    pages = {
        1: {"code": 0, "data": {"items": [{"workoutId": 10}, {"workoutId": 11}]}},
        2: {"code": 0, "data": {"items": [{"id": 12}]}},
        3: {"code": 0, "data": {"items": []}},
    }

    def fake_list(session, auth_headers, page_index, page_size):
        return pages[page_index]

    monkeypatch.setattr(workout, "list_custom_workouts", fake_list)
    session = workout.requests.Session()
    ids = workout.fetch_all_custom_workout_ids(session, {}, page_size=2)
    assert ids == {10, 11, 12}


def test_apply_uploaded_workout_map_updates_and_prunes():
    uploaded = {"1": 100, "2": 200, "3": 300}
    result = workout.WorkoutUploadResult(
        uploaded_map={"4": 400},
        pruned_keys=["2"],
    )
    workout.apply_uploaded_workout_map(uploaded, result)
    assert uploaded == {"1": 100, "3": 300, "4": 400}


def test_upload_workouts_skips_already_uploaded(monkeypatch):
    monkeypatch.setattr(workout, "login", lambda s, u, p: {"Authorization": "Bearer t"})
    monkeypatch.setattr(workout, "fetch_all_custom_workout_ids", lambda *a, **k: {100})
    monkeypatch.setattr(
        intervals_icu,
        "fetch_calendar_workouts",
        lambda *a, **k: [
            intervals_icu.CalendarWorkout(
                event_id=42,
                name="Done",
                description="",
                activity_type="Ride",
                workout_doc={"steps": [{"duration": 60}]},
            )
        ],
    )
    upload_calls: list = []
    monkeypatch.setattr(
        workout,
        "upload_custom_workout",
        lambda *a, **k: upload_calls.append(1) or 123,
    )

    cfg = workout.WorkoutUploadConfig(
        igp_user="u",
        igp_password="p",
        intervals_api_key="k",
        uploaded_workouts={"42": 100},
    )
    result = workout.upload_workouts(cfg)
    assert result.skipped == 1
    assert result.uploaded == 0
    assert upload_calls == []


def test_upload_workouts_reuploads_when_deleted_on_igpsport(monkeypatch):
    monkeypatch.setattr(workout, "login", lambda s, u, p: {"Authorization": "Bearer t"})
    monkeypatch.setattr(workout, "fetch_all_custom_workout_ids", lambda *a, **k: set())
    monkeypatch.setattr(
        intervals_icu,
        "fetch_calendar_workouts",
        lambda *a, **k: [
            intervals_icu.CalendarWorkout(
                event_id=42,
                name="Done",
                description="",
                activity_type="Ride",
                workout_doc={"steps": [{"duration": 60}]},
            )
        ],
    )
    monkeypatch.setattr(workout, "upload_custom_workout", lambda *a, **k: 200)

    cfg = workout.WorkoutUploadConfig(
        igp_user="u",
        igp_password="p",
        intervals_api_key="k",
        uploaded_workouts={"42": 100},
    )
    result = workout.upload_workouts(cfg)
    assert result.uploaded == 1
    assert result.uploaded_map == {"42": 200}
    assert result.pruned_keys == []


def test_upload_workouts_force_resync_updates_live_workout(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(workout, "login", lambda s, u, p: {"Authorization": "Bearer t"})
    monkeypatch.setattr(workout, "fetch_all_custom_workout_ids", lambda *a, **k: {100})
    monkeypatch.setattr(
        intervals_icu,
        "fetch_calendar_workouts",
        lambda *a, **k: [
            intervals_icu.CalendarWorkout(
                event_id=42,
                name="Update me",
                description="",
                activity_type="Ride",
                workout_doc={"steps": [{"duration": 60}]},
            )
        ],
    )

    def fake_upload(session, auth_headers, body):
        captured["body"] = body
        return 100

    monkeypatch.setattr(workout, "upload_custom_workout", fake_upload)

    cfg = workout.WorkoutUploadConfig(
        igp_user="u",
        igp_password="p",
        intervals_api_key="k",
        uploaded_workouts={"42": 100},
        force_resync=True,
    )
    result = workout.upload_workouts(cfg)
    assert result.uploaded == 1
    assert captured["body"]["data"]["id"] == "100"


def test_upload_workouts_prunes_stale_config_entries(monkeypatch):
    monkeypatch.setattr(workout, "login", lambda s, u, p: {"Authorization": "Bearer t"})
    monkeypatch.setattr(workout, "fetch_all_custom_workout_ids", lambda *a, **k: set())
    monkeypatch.setattr(intervals_icu, "fetch_calendar_workouts", lambda *a, **k: [])

    cfg = workout.WorkoutUploadConfig(
        igp_user="u",
        igp_password="p",
        intervals_api_key="k",
        uploaded_workouts={"99": 100},
    )
    result = workout.upload_workouts(cfg)
    assert result.pruned_keys == ["99"]


def test_upload_workouts_uploads_new_workout(monkeypatch):
    monkeypatch.setattr(workout, "login", lambda s, u, p: {"Authorization": "Bearer t"})
    monkeypatch.setattr(workout, "fetch_all_custom_workout_ids", lambda *a, **k: set())
    monkeypatch.setattr(
        intervals_icu,
        "fetch_calendar_workouts",
        lambda *a, **k: [
            intervals_icu.CalendarWorkout(
                event_id=7,
                name="New",
                description="",
                activity_type="Ride",
                workout_doc={"steps": [{"duration": 120, "power": {"value": 90, "units": "%ftp"}}]},
            )
        ],
    )
    monkeypatch.setattr(workout, "upload_custom_workout", lambda *a, **k: 555)

    cfg = workout.WorkoutUploadConfig(
        igp_user="u",
        igp_password="p",
        intervals_api_key="k",
    )
    result = workout.upload_workouts(cfg)
    assert result.uploaded == 1
    assert result.uploaded_map == {"7": 555}


def test_upload_workouts_skips_non_cycling_type(monkeypatch):
    monkeypatch.setattr(workout, "login", lambda s, u, p: {"Authorization": "Bearer t"})
    monkeypatch.setattr(workout, "fetch_all_custom_workout_ids", lambda *a, **k: set())
    monkeypatch.setattr(
        intervals_icu,
        "fetch_calendar_workouts",
        lambda *a, **k: [
            intervals_icu.CalendarWorkout(
                event_id=1,
                name="Run",
                description="",
                activity_type="Run",
                workout_doc={"steps": [{"duration": 60}]},
            )
        ],
    )
    result = workout.upload_workouts(
        workout.WorkoutUploadConfig(igp_user="u", igp_password="p", intervals_api_key="k")
    )
    assert result.skipped == 1
    assert result.uploaded == 0


def test_upload_workouts_one_day_window_uses_today_only(monkeypatch):
    captured: dict = {}
    today = date(2026, 6, 17)

    class FixedDate(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(workout, "date", FixedDate)
    monkeypatch.setattr(workout, "login", lambda s, u, p: {"Authorization": "Bearer t"})
    monkeypatch.setattr(workout, "fetch_all_custom_workout_ids", lambda *a, **k: set())

    def fake_fetch(api_key, oldest, newest):
        captured["oldest"] = oldest
        captured["newest"] = newest
        return []

    monkeypatch.setattr(intervals_icu, "fetch_calendar_workouts", fake_fetch)

    workout.upload_workouts(
        workout.WorkoutUploadConfig(
            igp_user="u",
            igp_password="p",
            intervals_api_key="k",
            workout_days_ahead=1,
        )
    )
    assert captured["oldest"] == today
    assert captured["newest"] == today
