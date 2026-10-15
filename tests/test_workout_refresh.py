"""Event identity and durable export metadata, using synthetic cloud I/O."""

from copy import deepcopy

import pytest

from intervalssync import intervals_icu
from intervalssync.igpsport import workout


def calendar_event(event_id=42, cadence=90):
    return intervals_icu.CalendarWorkout(
        event_id=event_id, name="Synthetic workout", description="",
        activity_type="Ride", workout_doc={"steps": [{
            "duration": 60, "power": {"value": 70, "units": "%ftp"},
            "cadence": {"value": cadence, "units": "rpm"},
        }]},
    )


def cloud(monkeypatch, events, live_ids, accepted_id=100, verifies=True):
    writes = []
    monkeypatch.setattr(workout, "login", lambda *a, **k: {})
    monkeypatch.setattr(workout, "fetch_all_custom_workout_ids", lambda *a, **k: set(live_ids))
    monkeypatch.setattr(intervals_icu, "fetch_calendar_workouts", lambda *a, **k: events)
    def upload(session, headers, body, **kwargs):
        writes.append(body)
        return accepted_id
    monkeypatch.setattr(workout, "upload_custom_workout", upload)
    monkeypatch.setattr(workout, "verify_custom_workout", lambda *a, **k: verifies)
    return writes


def config(mapping=None, state=None, **kwargs):
    cfg = workout.WorkoutUploadConfig("synthetic", "synthetic", "synthetic",
        uploaded_workouts=mapping or {}, **kwargs)
    cfg.workout_export_state = state or {}
    return cfg


def test_metadata_application_preserves_unrelated_legacy_mappings():
    mapping = {"41": 99, "42": 100}
    state = {}
    result = workout.WorkoutUploadResult(synced_map={"42": 100})
    result.workout_export_state = {"42": {"remote_id": 100, "verification_status": "pending"}}
    workout.apply_workout_state(mapping, state, result)
    assert mapping == {"41": 99, "42": 100}
    assert state == result.workout_export_state


def test_verified_same_event_unchanged_export_skips(monkeypatch):
    event = calendar_event()
    cloud(monkeypatch, [event], set())
    first = workout.upload_workouts(config())
    state = getattr(first, "workout_export_state", {})
    writes = cloud(monkeypatch, [event], {100})
    result = workout.upload_workouts(config({"42": 100}, state))
    assert result.skipped == 1
    assert writes == []


def test_changed_secondary_target_updates_same_remote_id(monkeypatch):
    cloud(monkeypatch, [calendar_event()], set())
    first = workout.upload_workouts(config())
    state = getattr(first, "workout_export_state", {})
    writes = cloud(monkeypatch, [calendar_event(cadence=95)], {100})
    result = workout.upload_workouts(config({"42": 100}, state))
    assert result.updated == 1
    assert writes[0]["data"]["id"] == "100"
    assert writes[0]["data"]["structure"][0]["secondaryIntensityTarget"]["minValue"] == 95
    assert getattr(result, "workout_export_state", {}).get("42", {}).get("verification_status") == "verified"


def test_replacement_event_never_claims_existing_remote_id(monkeypatch):
    cloud(monkeypatch, [calendar_event()], set())
    first = workout.upload_workouts(config())
    state = getattr(first, "workout_export_state", {})
    writes = cloud(monkeypatch, [calendar_event(event_id=43)], {100}, accepted_id=200)
    mapping = {"42": 100}
    result = workout.upload_workouts(config(mapping, state))
    workout.apply_workout_state(mapping, state, result)
    assert "id" not in writes[0]["data"]
    assert mapping == {"42": 100, "43": 200}


def test_pending_accepted_id_survives_failed_verification_and_restart(monkeypatch):
    writes = cloud(monkeypatch, [calendar_event()], set(), verifies=False)
    mapping, state, checkpoints = {}, {}, []
    def checkpoint(result):
        workout.apply_workout_state(mapping, state, result)
        checkpoints.append(deepcopy((mapping, state)))
    first = workout.upload_workouts(config(checkpoint=checkpoint))
    assert first.failed == first.verification_failed == 1
    assert checkpoints[0][0] == {"42": 100}
    assert checkpoints[0][1]["42"]["verification_status"] == "pending"
    assert checkpoints[0][1]["42"]["export_fingerprint"] is None
    writes = cloud(monkeypatch, [calendar_event()], {100})
    restarted = workout.upload_workouts(config(mapping, state))
    assert restarted.updated == 1
    assert writes[0]["data"]["id"] == "100"


def test_metadata_cannot_confirm_a_different_remote_mapping(monkeypatch):
    cloud(monkeypatch, [calendar_event()], set())
    first = workout.upload_workouts(config())
    state = getattr(first, "workout_export_state", {})
    writes = cloud(monkeypatch, [calendar_event()], {100, 200}, accepted_id=200)
    result = workout.upload_workouts(config({"42": 200}, state))
    assert result.updated == 1
    assert writes[0]["data"]["id"] == "200"
    assert getattr(result, "workout_export_state", {}).get("42", {}).get("remote_id") == 200


@pytest.mark.parametrize("mapping,live_ids", [({}, set()), ({"42": 100}, {100}), ({"42": 100}, set())])
@pytest.mark.parametrize("marker_field", ["name", "description"])
def test_skip_marker_blocks_create_update_and_recreation_even_when_forced(monkeypatch, mapping, live_ids, marker_field):
    event = calendar_event()
    setattr(event, marker_field, "Synthetic [skip-igp]")
    writes = cloud(monkeypatch, [event], live_ids)
    result = workout.upload_workouts(config(mapping, force_resync=True))
    assert result.skipped == 1
    assert writes == []


@pytest.mark.parametrize("accepted_id", [0, -1, True, "invalid", 1.5, None])
def test_invalid_api_workout_id_is_not_accepted(accepted_id):
    class Response:
        ok = True
        def raise_for_status(self):
            pass
        def json(self):
            return {"code": 0, "data": {"workoutId": accepted_id}}
    class Session:
        def post(self, *args, **kwargs):
            return Response()
    assert workout.upload_custom_workout(Session(), {}, {"data": {}}) is None
