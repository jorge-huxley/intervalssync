"""Tests for intervals.icu → Bryton workout upload."""

from __future__ import annotations

import pytest

from intervalssync import intervals_icu
from intervalssync.bryton import workout
from intervalssync.bryton.ddp import BrytonSession


class FakeResponse:
    def __init__(self, *, status=200, content=b"", ok=True):
        self.status_code = status
        self.content = content
        self.ok = ok if ok is not None else 200 <= status < 300

    def raise_for_status(self):
        if not self.ok:
            raise workout.requests.HTTPError(f"HTTP {self.status_code}")


def test_workout_doc_targets_hr_by_target_field():
    assert workout.workout_doc_targets_hr({"target": "HR", "steps": []}) is True
    assert workout.workout_doc_targets_hr({"target": "POWER", "steps": []}) is False


def test_workout_doc_targets_hr_by_step_hr_field():
    doc = {
        "target": "POWER",
        "steps": [{"duration": 300, "hr": {"value": 2, "units": "hr_zone"}}],
    }
    assert workout.workout_doc_targets_hr(doc) is True


def test_sanitize_workout_filename():
    assert workout._sanitize_workout_filename("Morning VO2", event_id=7) == "Morning_VO2"
    assert workout._sanitize_workout_filename("  ", event_id=7) == "icu_7"


def test_parse_workout_list_result():
    entries = workout._parse_workout_list_result(
        {
            "workout": [
                {
                    "id": "PEBSkSxcjqfcNiNCz",
                    "url": "/files/userFiles/PEBSkSxcjqfcNiNCz/original/PEBSkSxcjqfcNiNCz.fit",
                }
            ]
        }
    )
    assert len(entries) == 1
    assert workout._ids_from_file_entry(entries[0]) == {"PEBSkSxcjqfcNiNCz"}


def test_fetch_workout_library_parses_bryton_shape():
    session = BrytonSession(user_id="u1", auth_token="tok", host="active.brytonsport.com")

    def fake_call(_session, method, params):
        assert method == "user.file.list"
        return {
            "workout": [
                {"id": "abc123", "url": "/files/userFiles/abc123/original/abc123.fit"},
            ]
        }

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(workout, "call_method", fake_call)
    try:
        ids, names = workout._fetch_workout_library(session)
    finally:
        monkeypatch.undo()
    assert ids == {"abc123"}
    assert "abc123" in names


def test_stored_on_bryton_matches_id_or_legacy_filename():
    assert workout._stored_on_bryton("abc123", {"abc123"}, set()) is True
    assert workout._stored_on_bryton("Morning_Ride", set(), {"Morning_Ride"}) is True
    assert workout._stored_on_bryton("gone", {"other"}, set()) is False


def test_names_from_file_entry():
    assert workout._names_from_file_entry("bsWO0617_233758.fit") == {"bsWO0617_233758"}
    assert workout._names_from_file_entry({"name": "workout1.fit", "_id": "abc"}) == {
        "workout1",
        "abc",
    }


def _valid_fit_bytes() -> bytes:
    return b"\x00" * 8 + b".FIT" + b"\x00" * 6



def test_upload_workout_fit_posts_multipart():
    session = BrytonSession(user_id="user1", auth_token="tok", host="active.brytonsport.com")
    captured: dict = {}

    class FakeSession:
        def post(self, url, files, data, headers, timeout):
            captured["url"] = url
            captured["files"] = files
            captured["data"] = data
            captured["headers"] = headers
            return FakeResponse(status=200)

    ok = workout.upload_workout_fit(session, _valid_fit_bytes(), "Test Ride", http=FakeSession())
    assert ok is True
    assert captured["url"] == "https://active.brytonsport.com/workout/upload/user1"
    assert captured["files"]["file"][0] == "Test Ride.fit"
    assert captured["data"]["name"] == "Test Ride.fit"
    assert captured["data"]["provider"] == "bryton"
    assert captured["headers"]["X-User-Id"] == "user1"


def test_apply_uploaded_bryton_workout_map():
    uploaded = {"1": "old_name", "2": "gone"}
    result = workout.BrytonWorkoutUploadResult(
        uploaded_map={"1": "new_name"},
        pruned_keys=["2"],
    )
    workout.apply_uploaded_bryton_workout_map(uploaded, result)
    assert uploaded == {"1": "new_name"}


def test_upload_workouts_skips_already_uploaded(monkeypatch):
    session = BrytonSession(user_id="u1", auth_token="tok", host="active.brytonsport.com")

    class CW:
        event_id = 10
        name = "Existing"
        description = ""
        activity_type = "Ride"
        workout_doc = {"steps": [{"duration": 600}]}

    monkeypatch.setattr(workout, "web_login", lambda *a, **k: session)
    monkeypatch.setattr(workout, "_fetch_workout_library", lambda *a, **k: ({"stored"}, set()))
    monkeypatch.setattr(intervals_icu, "fetch_calendar_workouts", lambda *a, **k: [CW()])

    cfg = workout.BrytonWorkoutUploadConfig(
        bryton_email="a@b.com",
        bryton_password="pw",
        intervals_api_key="key",
        uploaded_workouts={"10": "stored"},
    )
    result = workout.upload_workouts(cfg)
    assert result.skipped == 1
    assert result.uploaded == 0


def test_upload_workouts_reuploads_when_deleted_on_bryton(monkeypatch):
    session = BrytonSession(user_id="u1", auth_token="tok", host="active.brytonsport.com")

    class CW:
        event_id = 10
        name = "Existing"
        description = ""
        activity_type = "Ride"
        workout_doc = {"steps": [{"duration": 600}]}

    fit = _valid_fit_bytes()

    monkeypatch.setattr(workout, "web_login", lambda *a, **k: session)
    monkeypatch.setattr(workout, "_fetch_workout_library", lambda *a, **k: (set(), set()))
    monkeypatch.setattr(intervals_icu, "fetch_calendar_workouts", lambda *a, **k: [CW()])
    monkeypatch.setattr(workout, "icu_workout_doc_to_bryton_fit", lambda *a, **k: fit)
    monkeypatch.setattr(workout, "upload_workout_fit", lambda *a, **k: True)

    cfg = workout.BrytonWorkoutUploadConfig(
        bryton_email="a@b.com",
        bryton_password="pw",
        intervals_api_key="key",
        uploaded_workouts={"10": "gone-id"},
    )
    result = workout.upload_workouts(cfg)
    assert result.uploaded == 1
    assert result.skipped == 0


def test_upload_workouts_uploads_new_workout(monkeypatch):
    session = BrytonSession(user_id="u1", auth_token="tok", host="active.brytonsport.com")

    class CW:
        event_id = 11
        name = "New VO2"
        description = ""
        activity_type = "Ride"
        workout_doc = {"steps": [{"duration": 600}]}

    fit = _valid_fit_bytes()

    monkeypatch.setattr(workout, "web_login", lambda *a, **k: session)
    monkeypatch.setattr(workout, "_fetch_workout_library", lambda *a, **k: (set(), set()))
    monkeypatch.setattr(intervals_icu, "fetch_calendar_workouts", lambda *a, **k: [CW()])
    monkeypatch.setattr(workout, "icu_workout_doc_to_bryton_fit", lambda *a, **k: fit)

    calls: list[str] = []

    def fake_upload(session, fit_bytes, name, *, http=None):
        calls.append(name)
        return True

    state = {"count": 0}

    def fake_fetch(_session):
        state["count"] += 1
        if state["count"] == 1:
            return set(), set()
        return {"new-file-id"}, set()

    monkeypatch.setattr(workout, "upload_workout_fit", fake_upload)
    monkeypatch.setattr(workout, "_fetch_workout_library", fake_fetch)

    cfg = workout.BrytonWorkoutUploadConfig(
        bryton_email="a@b.com",
        bryton_password="pw",
        intervals_api_key="key",
    )
    result = workout.upload_workouts(cfg)
    assert result.uploaded == 1
    assert result.uploaded_map["11"] == "new-file-id"


def test_upload_workouts_fetches_max_hr_only_for_hr_workouts(monkeypatch):
    session = BrytonSession(user_id="u1", auth_token="tok", host="active.brytonsport.com")

    class PowerWorkout:
        event_id = 20
        name = "Sweet Spot"
        description = ""
        activity_type = "Ride"
        workout_doc = {
            "target": "POWER",
            "steps": [{"duration": 600, "power": {"value": 90, "units": "%ftp"}}],
        }

    class HrWorkout:
        event_id = 21
        name = "HR Endurance"
        description = ""
        activity_type = "Ride"
        workout_doc = {
            "target": "HR",
            "steps": [
                {
                    "duration": 600,
                    "hr": {"value": 2, "units": "hr_zone"},
                    "_hr": {"start": 120.0, "end": 140.0},
                }
            ],
        }

    fit = _valid_fit_bytes()
    fetch_calls: list[str] = []
    encode_calls: list[float | None] = []

    monkeypatch.setattr(workout, "web_login", lambda *a, **k: session)
    monkeypatch.setattr(workout, "_fetch_workout_library", lambda *a, **k: (set(), set()))
    monkeypatch.setattr(
        intervals_icu,
        "fetch_calendar_workouts",
        lambda *a, **k: [PowerWorkout(), HrWorkout()],
    )

    def fake_fetch_max_hr(api_key, sport, *, http=None):
        fetch_calls.append(sport)
        return 193.0

    monkeypatch.setattr(intervals_icu, "fetch_sport_settings_max_hr", fake_fetch_max_hr)

    def fake_encode(name, workout_doc, *, max_hr=None):
        encode_calls.append(max_hr)
        return fit

    monkeypatch.setattr(workout, "icu_workout_doc_to_bryton_fit", fake_encode)
    monkeypatch.setattr(workout, "upload_workout_fit", lambda *a, **k: True)

    cfg = workout.BrytonWorkoutUploadConfig(
        bryton_email="a@b.com",
        bryton_password="pw",
        intervals_api_key="key",
    )
    result = workout.upload_workouts(cfg)
    assert result.uploaded == 2
    assert fetch_calls == ["Ride"]
    assert encode_calls == [None, 193.0]
