"""Tests for intervals.icu → iGPSPORT workout upload."""

from __future__ import annotations

from datetime import date

import pytest

from intervalssync import intervals_icu
from intervalssync.igpsport import workout


@pytest.fixture(autouse=True)
def verified_writes(request, monkeypatch):
    if request.node.get_closest_marker("real_verification"):
        return
    monkeypatch.setattr(
        workout, "verify_custom_workout", lambda *args, **kwargs: True, raising=False
    )


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


@pytest.mark.parametrize("items", [None, {}, "", [None], [{}], [{"id": 0}]])
def test_remote_listing_rejects_malformed_items(monkeypatch, items):
    monkeypatch.setattr(
        workout, "list_custom_workouts",
        lambda *a, **k: {"code": 0, "data": {"items": items}},
    )
    with pytest.raises(workout.SyncError):
        workout.fetch_all_custom_workout_ids(workout.requests.Session(), {})


def test_legacy_gui_map_tracks_recreated_remote_id():
    mapping = {"42": 100}
    result = workout.WorkoutUploadResult(recreated=1, synced_map={"42": 200})
    workout.apply_uploaded_workout_map(mapping, result)
    assert mapping == {"42": 200}


@pytest.mark.parametrize("payload", [{}, {"error": "unavailable"}, [None]])
def test_calendar_rejects_malformed_listing(monkeypatch, payload):
    class Client:
        def get(self, *args, **kwargs):
            return FakeResponse(json_data=payload)

    with pytest.raises(ValueError):
        intervals_icu.fetch_calendar_workouts(
            "synthetic", date(2026, 9, 10), date(2026, 9, 10), http=Client()
        )


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
        "unit": "PercentOfFtp",
        "value": 0,
        "minValue": 100,
        "maxValue": 100,
    }


@pytest.mark.parametrize("block", [
    {"reps": 2.5, "steps": [{"duration": 60}]},
    {"reps": 0, "steps": [{"duration": 60}]},
    {"reps": 2, "ramp": True, "steps": [{"duration": 60}]},
    {"reps": 2, "steps": [None, {"duration": 60}]},
    None,
])
def test_native_mapper_rejects_malformed_or_unsupported_repetitions(block):
    with pytest.raises(workout.UnsupportedWorkoutError):
        workout.icu_workout_doc_to_igps("Synthetic", "", {"steps": [block]})


@pytest.mark.real_verification
def test_native_verification_network_failure_returns_false(monkeypatch):
    def unavailable(*a, **k):
        raise workout.requests.Timeout("synthetic timeout")
    monkeypatch.setattr(workout, "fetch_custom_workout_detail", unavailable)
    assert not workout.verify_custom_workout(workout.requests.Session(), {}, 100, {"data": {}})


@pytest.mark.parametrize("primary,opposite", [("POWER", "_hr"), ("HR", "_power")])
def test_native_mapper_rejects_resolved_opposite_target(primary, opposite):
    with pytest.raises(workout.UnsupportedWorkoutError):
        workout.icu_workout_doc_to_igps("Synthetic", "", {
            "target": primary,
            "steps": [{"duration": 60, opposite: {"value": 150}}],
        })


def test_icu_workout_doc_maps_cadence_as_native_secondary_target():
    body = workout.icu_workout_doc_to_igps(
        "Cadence",
        "",
        {
            "target": "POWER",
            "steps": [
                {
                    "duration": 180,
                    "power": {"value": 2, "units": "power_zone"},
                    "_power": {"start": 140, "end": 180},
                    "cadence": {"start": 85, "end": 95, "units": "rpm"},
                }
            ],
        },
    )

    assert body is not None
    step = body["data"]["structure"][0]
    assert step["intensityTarget"] == {
        "unit": "PowerCustom",
        "value": 0,
        "minValue": 140,
        "maxValue": 180,
    }
    assert step["secondaryIntensityTarget"] == {
        "unit": "Cadence",
        "value": 0,
        "minValue": 85,
        "maxValue": 95,
    }
    assert "cadenceTarget" not in step


def test_icu_workout_doc_preserves_leaf_distance_over_estimated_duration():
    body = workout.icu_workout_doc_to_igps(
        "Distance",
        "",
        {"steps": [{"distance": 800, "duration": 96}]},
    )

    assert body is not None
    assert body["data"]["structure"][0]["length"] == {
        "unit": "Meter",
        "value": 800,
    }


def test_icu_workout_doc_uses_explicit_hr_target_instead_of_power():
    body = workout.icu_workout_doc_to_igps(
        "Heart rate",
        "",
        {
            "target": "HR",
            "steps": [
                {
                    "duration": 120,
                    "_power": {"start": 150, "end": 170},
                    "hr": {"value": 2, "units": "hr_zone"},
                    "_hr": {"start": 130, "end": 145},
                }
            ],
        },
    )

    assert body is not None
    assert body["data"]["structure"][0]["intensityTarget"] == {
        "unit": "HeartRateCustom",
        "value": 0,
        "minValue": 130,
        "maxValue": 145,
    }


def test_icu_workout_doc_rejects_an_explicit_unmapped_secondary_target():
    with pytest.raises(workout.UnsupportedWorkoutError, match="secondary heart-rate"):
        workout.icu_workout_doc_to_igps(
            "Power plus HR",
            "",
            {
                "target": "POWER",
                "steps": [
                    {
                        "duration": 60,
                        "power": {"value": 90, "units": "%ftp"},
                        "hr": {"value": 2, "units": "hr_zone"},
                    }
                ],
            },
        )


def test_icu_workout_doc_rejects_ramp_before_any_remote_write():
    with pytest.raises(workout.UnsupportedWorkoutError, match="ramp"):
        workout.icu_workout_doc_to_igps(
            "Ramp",
            "",
            {
                "target": "POWER",
                "steps": [
                    {
                        "duration": 300,
                        "ramp": True,
                        "power": {"start": 50, "end": 70, "units": "%ftp"},
                    }
                ],
            },
        )


def test_icu_workout_doc_prefers_resolved_power_watts():
    doc = {
        "steps": [
            {
                "duration": 600,
                "warmup": True,
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


def test_low_power_first_and_last_steps_remain_active_without_explicit_marks():
    body = workout.icu_workout_doc_to_igps(
        "No inferred classifications",
        "",
        {
            "steps": [
                {"duration": 300, "power": {"value": 40, "units": "%ftp"}},
                {"duration": 300, "power": {"value": 100, "units": "%ftp"}},
                {"duration": 300, "power": {"value": 35, "units": "%ftp"}},
            ]
        },
    )
    assert [step["intensityClass"] for step in body["data"]["structure"]] == [
        "Active",
        "Active",
        "Active",
    ]


def test_icu_workout_doc_includes_existing_id_for_update():
    doc = {"steps": [{"duration": 60}]}
    body = workout.icu_workout_doc_to_igps("Update", "", doc, existing_workout_id=5012)
    assert body is not None
    assert body["data"]["id"] == "5012"


def test_upload_custom_workout_returns_id(monkeypatch):
    captured = {}

    def fake_post(self, *args, **kwargs):
        captured.update(kwargs)
        return FakeResponse(json_data={"code": 0, "data": {"workoutId": 999}})

    monkeypatch.setattr(
        workout.requests.Session,
        "post",
        fake_post,
    )
    session = workout.requests.Session()
    wid = workout.upload_custom_workout(
        session, {"Authorization": "Bearer x"}, {"data": {}}
    )
    assert wid == 999
    assert captured["timeout"] == (10, 30)


def test_upload_custom_workout_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(
        workout.requests.Session,
        "post",
        lambda self, *a, **k: FakeResponse(status=400, json_data={"code": 1}),
    )
    session = workout.requests.Session()
    assert workout.upload_custom_workout(session, {}, {}) is None


@pytest.mark.real_verification
def test_verify_custom_workout_compares_secondary_target_and_ignores_ids(monkeypatch):
    expected = workout.icu_workout_doc_to_igps(
        "Verified",
        "",
        {
            "target": "POWER",
            "steps": [
                {
                    "duration": 60,
                    "power": {"value": 90, "units": "%ftp"},
                    "cadence": {"start": 85, "end": 95, "units": "rpm"},
                }
            ],
        },
    )
    assert expected is not None
    remote_step = dict(expected["data"]["structure"][0], id="step-id", uuid="remote-uuid")
    remote = {"code": 0, "data": {"title": "Verified", "structure": [remote_step]}}
    captured = {}

    def fake_get(self, url, **kwargs):
        captured.update(url=url, params=kwargs["params"])
        return FakeResponse(json_data=remote)

    monkeypatch.setattr(workout.requests.Session, "get", fake_get)

    assert workout.verify_custom_workout(
        workout.requests.Session(), {}, 123, expected
    )
    assert captured["url"].endswith("/WorkOut/GetWorkOutDetail")
    assert captured["params"] == {"id": 123}


@pytest.mark.parametrize(
    "target",
    [
        {"unit": "Power", "value": 3},
        {"unit": "PowerCustom", "value": 0, "minValue": 150, "maxValue": 180},
        {"unit": "PercentOfFtp", "value": 0, "minValue": 92, "maxValue": 105},
        {"unit": "HeartRate", "value": 4},
        {
            "unit": "HeartRateCustom",
            "value": 0,
            "minValue": 130,
            "maxValue": 145,
        },
        {"unit": "Speed", "value": 0, "minValue": 5000, "maxValue": 6944},
    ],
)
def test_verification_shape_retains_every_observed_primary_target(target):
    data = {
        "title": "Native contract",
        "structure": [
            {
                "type": "Step",
                "intensityClass": "Active",
                "openDuration": "false",
                "length": {"unit": "Second", "value": 60},
                "intensityTarget": target,
                "secondaryIntensityTarget": {
                    "unit": "Cadence",
                    "value": 0,
                    "minValue": 85,
                    "maxValue": 95,
                },
            }
        ],
    }

    assert workout._verification_shape(data) == data


@pytest.mark.parametrize(
    "secondary_target",
    [
        {"unit": "Cadence", "value": 0, "minValue": 85, "maxValue": 95},
        {"unit": "HeartRate", "value": 4},
        {
            "unit": "HeartRateCustom",
            "value": 0,
            "minValue": 130,
            "maxValue": 145,
        },
        {"unit": "Power", "value": 3},
    ],
)
def test_verification_shape_retains_every_observed_secondary_target(secondary_target):
    data = {
        "title": "Native secondary contract",
        "structure": [
            {
                "type": "Step",
                "intensityClass": "Active",
                "openDuration": "false",
                "length": {"unit": "Second", "value": 60},
                "intensityTarget": {"unit": "Power", "value": 2},
                "secondaryIntensityTarget": secondary_target,
            }
        ],
    }

    assert workout._verification_shape(data) == data


def test_icu_workout_doc_preserves_distance_inside_a_repetition():
    body = workout.icu_workout_doc_to_igps(
        "Repeated distance",
        "",
        {
            "steps": [
                {
                    "reps": 2,
                    "distance": 1600,
                    "duration": 432,
                    "steps": [
                        {"distance": 800, "duration": 96},
                        {"duration": 120},
                    ],
                }
            ]
        },
    )

    assert body is not None
    repeated = body["data"]["structure"][0]
    assert repeated["length"] == {"unit": "Repetition", "value": 2}
    assert repeated["steps"][0]["length"] == {"unit": "Meter", "value": 800}
    assert repeated["steps"][1]["length"] == {"unit": "Second", "value": 120}


def test_list_custom_workouts(monkeypatch):
    captured: dict = {}

    def fake_get(self, url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        captured["timeout"] = kwargs.get("timeout")
        return FakeResponse(json_data={"code": 0, "data": {"items": []}})

    monkeypatch.setattr(workout.requests.Session, "get", fake_get)
    session = workout.requests.Session()
    workout.list_custom_workouts(
        session, {"Authorization": "Bearer t"}, page_index=2, page_size=5
    )
    assert captured["url"] == workout.IGPS_WORKOUT_LIST_URL
    assert captured["params"] == {"PageIndex": 2, "PageSize": 5}
    assert captured["timeout"] == (10, 30)


def test_list_custom_workouts_china_region(monkeypatch):
    captured: dict = {}

    def fake_get(self, url, **kwargs):
        captured["url"] = url
        return FakeResponse(json_data={"code": 0, "data": {"items": []}})

    monkeypatch.setattr(workout.requests.Session, "get", fake_get)
    session = workout.requests.Session()
    workout.list_custom_workouts(session, {"Authorization": "Bearer t"}, region="china")
    assert (
        captured["url"]
        == "https://prod.zh.igpsport.com/service/mobile/api/WorkOut/CustomWorkout"
    )


def test_fetch_all_custom_workout_ids_paginates(monkeypatch):
    pages = {
        1: {"code": 0, "data": {"items": [{"workoutId": 10}, {"workoutId": 11}]}},
        2: {"code": 0, "data": {"items": [{"id": 12}]}},
        3: {"code": 0, "data": {"items": []}},
    }

    def fake_list(session, auth_headers, page_index, page_size, **kwargs):
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


def test_upload_workouts_seeds_legacy_mapping_with_update(monkeypatch):
    monkeypatch.setattr(
        workout, "login", lambda s, u, p, *a, **k: {"Authorization": "Bearer t"}
    )
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
        lambda *a, **k: upload_calls.append(1) or 100,
    )

    cfg = workout.WorkoutUploadConfig(
        igp_user="u",
        igp_password="p",
        intervals_api_key="k",
        uploaded_workouts={"42": 100},
    )
    result = workout.upload_workouts(cfg)
    assert result.updated == 1
    assert result.uploaded == 0
    assert upload_calls == [1]


def test_upload_workouts_reuploads_when_deleted_on_igpsport(monkeypatch):
    monkeypatch.setattr(
        workout, "login", lambda s, u, p, *a, **k: {"Authorization": "Bearer t"}
    )
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
    assert result.recreated == 1
    assert result.uploaded == 0
    assert result.synced_map == {"42": 200}
    assert result.pruned_keys == []


def test_upload_workouts_force_resync_updates_live_workout(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        workout, "login", lambda s, u, p, *a, **k: {"Authorization": "Bearer t"}
    )
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

    def fake_upload(session, auth_headers, body, **kwargs):
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
    assert result.updated == 1
    assert result.uploaded == 0
    assert captured["body"]["data"]["id"] == "100"


def test_upload_workouts_prunes_stale_config_entries(monkeypatch):
    monkeypatch.setattr(
        workout, "login", lambda s, u, p, *a, **k: {"Authorization": "Bearer t"}
    )
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
    monkeypatch.setattr(
        workout, "login", lambda s, u, p, *a, **k: {"Authorization": "Bearer t"}
    )
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
                workout_doc={
                    "steps": [
                        {"duration": 120, "power": {"value": 90, "units": "%ftp"}}
                    ]
                },
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


def test_upload_workouts_keeps_accepted_id_pending_after_verification_failure(
    monkeypatch,
):
    current = _calendar_workout()
    _patch_workout_io(monkeypatch, [current], set(), 555)
    monkeypatch.setattr(workout, "verify_custom_workout", lambda *args, **kwargs: False)

    result = workout.upload_workouts(workout.WorkoutUploadConfig("u", "p", "k"))

    assert result.uploaded == 0
    assert result.verification_failed == 1
    assert result.failed == 1
    assert result.synced_map == {}
    assert result.workout_export_state["42"] == {
        "remote_id": 555,
        "export_fingerprint": None,
        "verification_version": None,
        "verification_status": "pending",
    }


def test_upload_workouts_aborts_when_pending_id_checkpoint_fails(monkeypatch):
    current = _calendar_workout()
    _patch_workout_io(monkeypatch, [current], set(), 555)

    def broken_checkpoint(result):
        raise OSError("state volume unavailable")

    with pytest.raises(workout.SyncError, match="checkpoint accepted workout ID"):
        workout.upload_workouts(
            workout.WorkoutUploadConfig("u", "p", "k", checkpoint=broken_checkpoint)
        )


def test_upload_workouts_skips_non_cycling_type(monkeypatch):
    monkeypatch.setattr(
        workout, "login", lambda s, u, p, *a, **k: {"Authorization": "Bearer t"}
    )
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
        workout.WorkoutUploadConfig(
            igp_user="u", igp_password="p", intervals_api_key="k"
        )
    )
    assert result.skipped == 1
    assert result.uploaded == 0


def test_upload_workouts_blocks_unsupported_workout_and_continues(monkeypatch):
    blocked = _calendar_workout(
        event_id=41,
        name="Unsupported ramp",
        steps=[
            {
                "duration": 60,
                "ramp": True,
                "power": {"value": 90, "units": "%ftp"},
            }
        ],
    )
    supported = _calendar_workout(
        event_id=42,
        name="Supported",
        start_date_local="2026-09-11",
        steps=[{"duration": 60}],
    )
    original = {
        "remote_id": 100,
        "export_fingerprint": "old",
        "verification_version": None,
        "verification_status": None,
    }
    calls = _patch_workout_io(monkeypatch, [blocked, supported], {100}, 200)

    result = workout.upload_workouts(
        workout.WorkoutUploadConfig(
            "u", "p", "k", uploaded_workouts={"41": 100},
            workout_export_state={"41": dict(original)}
        )
    )

    assert result.unsupported == 1
    assert result.failed == 1
    assert result.uploaded == 1
    assert len(calls) == 1
    assert result.workout_export_state["41"] == original


def test_upload_workouts_one_day_window_uses_today_only(monkeypatch):
    captured: dict = {}
    today = date(2026, 6, 17)

    class FixedDate(date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(workout, "date", FixedDate)
    monkeypatch.setattr(
        workout, "login", lambda s, u, p, *a, **k: {"Authorization": "Bearer t"}
    )
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


def _calendar_workout(
    *,
    event_id=42,
    name="Workout",
    description="",
    start_date_local="2026-09-10",
    steps=None,
):
    return intervals_icu.CalendarWorkout(
        event_id=event_id,
        name=name,
        description=description,
        activity_type="Ride",
        workout_doc={"steps": steps or [{"duration": 60}]},
        start_date=start_date_local,
    )


def _patch_workout_io(monkeypatch, calendar, live_ids, returned_id=100):
    monkeypatch.setattr(workout, "login", lambda *a, **k: {"Authorization": "Bearer t"})
    monkeypatch.setattr(
        workout, "fetch_all_custom_workout_ids", lambda *a, **k: set(live_ids)
    )
    monkeypatch.setattr(
        intervals_icu, "fetch_calendar_workouts", lambda *a, **k: calendar
    )
    calls = []

    def fake_upload(*args, **kwargs):
        calls.append(args[2])
        return returned_id

    monkeypatch.setattr(workout, "upload_custom_workout", fake_upload)
    return calls


def test_event_description_precedes_nested_description_and_counts_truncation(
    monkeypatch,
):
    event_description = "E" * 501
    body = workout.icu_workout_doc_to_igps(
        "Workout",
        event_description,
        {"description": "nested", "steps": [{"duration": 60}]},
    )
    assert body["data"]["description"] == "E" * 500

    calls = _patch_workout_io(
        monkeypatch, [_calendar_workout(description=event_description)], set(), 101
    )
    result = workout.upload_workouts(workout.WorkoutUploadConfig("u", "p", "k"))
    assert len(calls) == 1
    assert result.description_truncated == 1


def test_unstructured_current_workout_retains_missing_remote_mapping(monkeypatch):
    current = _calendar_workout()
    first_calls = _patch_workout_io(monkeypatch, [current], set(), 100)
    first = workout.upload_workouts(workout.WorkoutUploadConfig("u", "p", "k"))
    current.workout_doc.clear()
    calls = _patch_workout_io(monkeypatch, [current], set(), 200)
    result = workout.upload_workouts(workout.WorkoutUploadConfig(
        "u", "p", "k", uploaded_workouts={"42": 100},
        workout_export_state=first.workout_export_state,
    ))
    assert calls == []
    assert result.workout_export_state == first.workout_export_state


def test_calendar_keeps_identity_when_document_is_missing(monkeypatch):
    class Client:
        def get(self, *a, **k):
            return FakeResponse(json_data=[{
                "id": 42, "category": "WORKOUT", "external_id": "plan-42",
                "oauth_client_id": "provider", "start_date_local": "2026-09-10",
            }])
    result = intervals_icu.fetch_calendar_workouts(
        "synthetic", date(2026, 9, 10), date(2026, 9, 10), http=Client(),
    )
    assert len(result) == 1
    assert result[0].event_id == 42
    assert result[0].start_date == "2026-09-10"
    assert result[0].workout_doc == {}


def test_duplicate_event_ids_abort_before_any_write(monkeypatch):
    calls = _patch_workout_io(
        monkeypatch, [_calendar_workout(), _calendar_workout()], set()
    )
    with pytest.raises(workout.SyncError, match="ambiguous"):
        workout.upload_workouts(workout.WorkoutUploadConfig("u", "p", "k"))
    assert calls == []


def test_changed_workout_updates_same_remote_id(monkeypatch):
    current = _calendar_workout(name="Changed")
    calls = _patch_workout_io(monkeypatch, [current], {100}, 100)
    cfg = workout.WorkoutUploadConfig(
        "u", "p", "k", uploaded_workouts={"42": 100},
        workout_export_state={"42": {
            "remote_id": 100, "export_fingerprint": "old",
            "verification_version": 1, "verification_status": "verified",
        }},
    )
    result = workout.upload_workouts(cfg)
    assert result.updated == 1
    assert result.uploaded == 0
    assert calls[0]["data"]["id"] == "100"
    assert result.synced_map == {"42": 100}

def test_unchanged_workout_is_skipped_without_write(monkeypatch):
    current = _calendar_workout()
    body = workout.icu_workout_doc_to_igps(
        current.name, current.description, current.workout_doc, existing_workout_id=100
    )
    fingerprint = workout.export_fingerprint(body)
    calls = _patch_workout_io(monkeypatch, [current], {100}, 100)
    cfg = workout.WorkoutUploadConfig(
        "u",
        "p",
        "k",
        uploaded_workouts={"42": 100},
        workout_export_state={
            "42": {
                "remote_id": 100,
                "export_fingerprint": fingerprint,
            }
        },
    )
    result = workout.upload_workouts(cfg)
    assert result.skipped == 1
    assert result.updated == 0
    assert calls == []


def test_missing_mapped_workout_is_recreated_in_active_window(monkeypatch):
    current = _calendar_workout()
    calls = _patch_workout_io(monkeypatch, [current], set(), 200)
    cfg = workout.WorkoutUploadConfig(
        "u",
        "p",
        "k",
        uploaded_workouts={"42": 100},
        workout_export_state={
            "42": {
                "remote_id": 100,
                "export_fingerprint": "old",
            }
        },
    )
    result = workout.upload_workouts(cfg)
    assert result.recreated == 1
    assert result.uploaded == 0
    assert "id" not in calls[0]["data"]
    assert result.workout_export_state["42"]["remote_id"] == 200


def test_skip_marker_suppresses_create_update_and_force(monkeypatch):
    current = _calendar_workout(name="Intervals [skip-igp]")
    calls = _patch_workout_io(monkeypatch, [current], {100}, 100)
    cfg = workout.WorkoutUploadConfig(
        "u", "p", "k", uploaded_workouts={"42": 100}, force_resync=True
    )
    result = workout.upload_workouts(cfg)
    assert result.skipped == 1
    assert calls == []


def test_ignore_marker_is_ordinary_text(monkeypatch):
    current = _calendar_workout(name="Intervals [ignore-igp]")
    calls = _patch_workout_io(monkeypatch, [current], set(), 100)
    result = workout.upload_workouts(workout.WorkoutUploadConfig("u", "p", "k"))
    assert result.uploaded == 1
    assert len(calls) == 1


def test_update_id_mismatch_fails_and_preserves_record(monkeypatch):
    current = _calendar_workout()
    original = {
        "remote_id": 100,
        "export_fingerprint": "old",
        "verification_version": None,
        "verification_status": None,
    }
    _patch_workout_io(monkeypatch, [current], {100}, 999)
    cfg = workout.WorkoutUploadConfig(
        "u", "p", "k", uploaded_workouts={"42": 100},
        workout_export_state={"42": dict(original)}
    )
    result = workout.upload_workouts(cfg)
    assert result.failed == 1
    assert result.updated == 0
    assert result.workout_export_state["42"] == original


def test_incomplete_remote_listing_fails_closed(monkeypatch):
    monkeypatch.setattr(
        workout,
        "list_custom_workouts",
        lambda *a, **k: {"code": 7, "message": "temporary"},
    )
    with pytest.raises(workout.SyncError):
        workout.fetch_all_custom_workout_ids(workout.requests.Session(), {})
