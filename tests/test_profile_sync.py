"""Tests for intervals.icu → iGPSPORT profile sync orchestration."""

from __future__ import annotations

import copy

import pytest

from intervalssync.igpsport.profile_sync import (
    _verify_interval_state,
    RiderSettingsSyncConfig,
    ProfileSyncConfig,
    apply_intervals_settings,
    build_rider_settings_plan,
    compare_profile_thresholds,
    parse_rider_fields,
    sync_rider_settings,
)
from intervalssync.intervals_icu import AthleteSettings, SportSettings


def _igpsport_payload(*, power_count: int = 7, hr_count: int = 5) -> dict:
    return {
        "member": {
            "ftp": 240,
            "mhr": 190,
            "lthr": 150,
            "heartRateComputeMode": 2,
            "quietHeartRate": 60,
        },
        "power": [{"id": index, "start": 0, "end": 100 + index} for index in range(power_count)],
        "heartRate": [{"id": index, "start": 0, "end": 100 + index} for index in range(hr_count)],
    }


FRIEL_NAMES = [
    "Recovery",
    "Aerobic",
    "Tempo",
    "SubThreshold",
    "SuperThreshold",
    "Aerobic Capacity",
    "Anaerobic",
]
COGGAN_NAMES = [
    "Active Recovery",
    "Endurance",
    "Tempo",
    "Threshold",
    "VO2 Max",
    "Anaerobic",
    "Neuromuscular",
]


def _rider_source() -> tuple[SportSettings, AthleteSettings]:
    return (
        SportSettings(
            ftp=230,
            lthr=180,
            max_hr=195,
            power_zones=[55, 75, 90, 105, 120, 150, 999],
            hr_zones=[120, 140, 160, 175, 185, 190, 195],
            power_zone_names=COGGAN_NAMES,
            hr_zone_names=FRIEL_NAMES,
        ),
        AthleteSettings(
            resting_hr=48,
            weight=72.34,
            height_cm=178,
            birth_date="1990-01-02",
            sex=1,
        ),
    )


def _rider_interval_destination() -> dict:
    return {
        "member": {
            "ftp": 220,
            "mhr": 190,
            "lthr": 170,
            "heartRateComputeMode": 0,
            "quietHeartRate": 55,
            "unrelated": "keep",
        },
        "power": [
            {
                "id": i,
                "start": 0,
                "end": 2000 if i == 6 else 100 + i,
                "color": f"p{i}",
            }
            for i in range(7)
        ],
        "heartRate": [
            {"id": i, "start": 0, "end": 130 + i, "color": f"m{i}"}
            for i in range(5)
        ],
        "heartRateReserve": [
            {"id": i, "start": 0, "end": 140 + i, "color": f"r{i}"}
            for i in range(5)
        ],
        "heartRateLactateThreshold": [
            {"id": i, "start": 0, "end": 150 + i, "color": f"l{i}"}
            for i in range(5)
        ],
    }


def _rider_user_destination() -> dict:
    return {
        "cityId": 12345,
        "areaId": 12345,
        "sex": 2,
        "height": 165,
        "nickName": "Preserve Me",
        "birthDate": "1985-05-06",
        "weight": 80.0,
        "unrelated": "keep",
    }


@pytest.mark.parametrize("metric", ["hr_zones", "power_zones"])
def test_malformed_destination_zones_block_interval_group(metric):
    sport, athlete = _rider_source()
    destination = _rider_interval_destination()
    table = "power" if metric == "power_zones" else "heartRate"
    destination[table][1] = None
    plan = build_rider_settings_plan(
        sport, athlete, destination, _rider_user_destination(), parse_rider_fields(metric)
    )
    assert plan.interval_changed_fields == ()
    assert plan.field_statuses[metric] == "invalid"


def test_rounded_power_collision_uses_legacy_boundary_repair():
    sport, athlete = _rider_source()
    from dataclasses import replace
    sport = replace(sport, ftp=200, power_zones=[55, 55.1, 55.2, 55.3, 55.4, 150, 999])
    plan = build_rider_settings_plan(
        sport, athlete, _rider_interval_destination(), _rider_user_destination(),
        parse_rider_fields("power_zones"),
    )
    assert plan.field_statuses["power_zones"] == "would_update"
    assert [row["end"] for row in plan.interval_body["power"]] == [110, 111, 112, 113, 114, 300, 2500]


def test_interval_only_plan_does_not_parse_unselected_personal_values():
    sport, athlete = _rider_source()
    user = _rider_user_destination()
    user["gender"] = "malformed"
    plan = build_rider_settings_plan(
        sport, athlete, _rider_interval_destination(), user, parse_rider_fields("ftp")
    )
    assert plan.interval_changed_fields == ("ftp",)
    assert plan.personal_changed_fields == ()


def test_parse_rider_fields_defaults_to_all_and_expands_dependencies():
    all_fields = parse_rider_fields(None)
    selected = parse_rider_fields("hr_zones,power_zones")

    assert len(all_fields.requested) == 10
    assert all_fields.requested == all_fields.effective
    assert selected.requested == ("power_zones", "hr_zones")
    assert selected.effective == (
        "ftp",
        "power_zones",
        "max_hr",
        "lthr",
        "hr_zones",
    )


@pytest.mark.parametrize("raw", ["ftp,ftp", "ftp,,lthr", "unknown"])
def test_parse_rider_fields_rejects_duplicates_empty_members_and_unknowns(raw):
    with pytest.raises(ValueError):
        parse_rider_fields(raw)


def test_build_rider_plan_uses_legacy_max_hr_table_and_mode():
    sport, athlete = _rider_source()
    current = _rider_interval_destination()

    plan = build_rider_settings_plan(
        sport,
        athlete,
        current,
        _rider_user_destination(),
        parse_rider_fields("hr_zones"),
    )

    assert plan.interval_body["member"]["heartRateComputeMode"] == 0
    assert plan.interval_body["member"]["lthr"] == 180
    assert plan.interval_body["member"]["mhr"] == 195
    assert [
        zone["end"] for zone in plan.interval_body["heartRate"]
    ] == [120, 140, 160, 175, 195]
    assert plan.interval_body["heartRateLactateThreshold"] == current["heartRateLactateThreshold"]
    assert plan.interval_body["heartRateReserve"] == current["heartRateReserve"]
    assert plan.interval_body["member"]["unrelated"] == "keep"


def test_build_rider_plan_five_hr_bounds_use_legacy_max_hr_table():
    _sport, athlete = _rider_source()
    sport = SportSettings(
        ftp=None,
        lthr=None,
        max_hr=195,
        power_zones=[],
        hr_zones=[120, 145, 165, 180, 195],
        hr_zone_names=["Recovery", "Endurance", "Tempo", "Threshold", "VO2 Max"],
    )
    current = _rider_interval_destination()
    current["member"]["heartRateComputeMode"] = 1

    plan = build_rider_settings_plan(
        sport,
        athlete,
        current,
        _rider_user_destination(),
        parse_rider_fields("hr_zones"),
    )

    assert plan.interval_body["member"]["heartRateComputeMode"] == 0
    assert [zone["end"] for zone in plan.interval_body["heartRate"]] == [
        120,
        145,
        165,
        180,
        195,
    ]
    assert plan.interval_body["heartRateReserve"] == current["heartRateReserve"]
    assert plan.interval_body["heartRateLactateThreshold"] == current[
        "heartRateLactateThreshold"
    ]


def test_build_rider_plan_uses_legacy_power_rounding_and_terminal_cap():
    sport, athlete = _rider_source()
    current = _rider_interval_destination()
    current["power"][-1]["end"] = 2000

    plan = build_rider_settings_plan(
        sport,
        athlete,
        current,
        _rider_user_destination(),
        parse_rider_fields("power_zones"),
    )

    assert plan.interval_body["member"]["ftp"] == 230
    assert [zone["end"] for zone in plan.interval_body["power"]] == [
        126,
        172,
        207,
        242,
        276,
        345,
        2500,
    ]
    assert [zone["color"] for zone in plan.interval_body["power"]] == [
        f"p{i}" for i in range(7)
    ]


def test_build_rider_plan_personal_payload_preserves_unselected_required_fields():
    sport, athlete = _rider_source()

    plan = build_rider_settings_plan(
        sport,
        athlete,
        _rider_interval_destination(),
        _rider_user_destination(),
        parse_rider_fields("height,birth_date"),
    )

    assert plan.personal_payload == {
        "areaId": 12345,
        "birthDate": "1990-01-02",
        "gender": 2,
        "height": 178,
        "nickName": "Preserve Me",
        "weight": 80.0,
    }
    assert plan.field_statuses["height"] == "would_update"
    assert plan.field_statuses["birth_date"] == "would_update"


def test_build_rider_plan_refuses_personal_write_when_required_value_is_missing():
    sport, athlete = _rider_source()
    current_user = _rider_user_destination()
    del current_user["weight"]

    plan = build_rider_settings_plan(
        sport,
        athlete,
        _rider_interval_destination(),
        current_user,
        parse_rider_fields("height"),
    )

    assert plan.field_statuses["height"] == "invalid"
    assert plan.personal_changed_fields == ()


def test_build_rider_plan_missing_source_does_not_clear_destination():
    sport, athlete = _rider_source()
    athlete = AthleteSettings(None, None, None, None, None)

    plan = build_rider_settings_plan(
        sport,
        athlete,
        _rider_interval_destination(),
        _rider_user_destination(),
        parse_rider_fields("weight,height,birth_date,sex,resting_hr"),
    )

    assert set(plan.field_statuses.values()) == {"source_missing"}
    assert plan.personal_changed_fields == ()
    assert plan.interval_changed_fields == ()


def test_build_rider_plan_invalid_zone_shape_blocks_interval_group():
    sport, athlete = _rider_source()
    sport = SportSettings(
        **{
            **sport.__dict__,
            "invalid_fields": frozenset({"hr_zones"}),
        }
    )

    plan = build_rider_settings_plan(
        sport,
        athlete,
        _rider_interval_destination(),
        _rider_user_destination(),
        parse_rider_fields("ftp,hr_zones"),
    )

    assert plan.field_statuses["hr_zones"] == "invalid"
    assert plan.field_statuses["ftp"] == "invalid"
    assert plan.interval_changed_fields == ()


def test_sync_rider_settings_writes_each_changed_group_once_and_verifies(monkeypatch):
    from intervalssync.igpsport import profile_sync

    sport, athlete = _rider_source()
    current_interval = _rider_interval_destination()
    current_interval["power"][-1]["end"] = 2000
    current_user = _rider_user_destination()
    interval_posts: list[dict] = []
    personal_posts: list[dict] = []
    state = {"interval": current_interval, "user": current_user}

    monkeypatch.setattr(profile_sync, "login", lambda *a, **k: {"Authorization": "Bearer x"})
    monkeypatch.setattr(profile_sync, "member_id_from_token", lambda *a, **k: 1)
    monkeypatch.setattr(profile_sync.intervals_icu, "fetch_sport_settings", lambda *a, **k: sport)
    monkeypatch.setattr(profile_sync.intervals_icu, "fetch_athlete_settings", lambda *a, **k: athlete)
    monkeypatch.setattr(profile_sync, "fetch_personal_interval_info", lambda *a, **k: copy.deepcopy(state["interval"]))
    monkeypatch.setattr(profile_sync, "fetch_user_info", lambda *a, **k: copy.deepcopy(state["user"]))

    def post_interval(_session, _headers, body, *_args, **_kwargs):
        interval_posts.append(copy.deepcopy(body))
        state["interval"] = copy.deepcopy(body)
        return {"code": 0}

    def post_personal(_session, _headers, body, *_args, **_kwargs):
        personal_posts.append(copy.deepcopy(body))
        state["user"].update(
            weight=body["weight"],
            height=body["height"],
            birthDate=body["birthDate"],
            sex=body["gender"],
            cityId=body["areaId"],
            nickName=body["nickName"],
        )
        return {"code": 0}

    monkeypatch.setattr(profile_sync, "update_personal_interval_info", post_interval)
    monkeypatch.setattr(profile_sync, "update_personal_user_info", post_personal)

    result = sync_rider_settings(
        RiderSettingsSyncConfig("user", "pass", "api", fields=None)
    )

    assert len(interval_posts) == 1
    assert len(personal_posts) == 1
    assert result.failed == 0
    assert result.verified > 0
    assert set(result.field_statuses.values()) <= {"verified", "unchanged"}


def test_sync_rider_settings_continues_personal_group_after_interval_write_failure(monkeypatch):
    from intervalssync.igpsport import profile_sync

    sport, athlete = _rider_source()
    current_user = _rider_user_destination()
    personal_posts: list[dict] = []
    monkeypatch.setattr(profile_sync, "login", lambda *a, **k: {"Authorization": "Bearer x"})
    monkeypatch.setattr(profile_sync, "member_id_from_token", lambda *a, **k: 1)
    monkeypatch.setattr(profile_sync.intervals_icu, "fetch_sport_settings", lambda *a, **k: sport)
    monkeypatch.setattr(profile_sync.intervals_icu, "fetch_athlete_settings", lambda *a, **k: athlete)
    monkeypatch.setattr(profile_sync, "fetch_personal_interval_info", lambda *a, **k: _rider_interval_destination())
    monkeypatch.setattr(profile_sync, "fetch_user_info", lambda *a, **k: copy.deepcopy(current_user))
    monkeypatch.setattr(profile_sync, "update_personal_interval_info", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("private")))

    def post_personal(_session, _headers, body, *_args, **_kwargs):
        personal_posts.append(body)
        current_user.update(weight=body["weight"], height=body["height"], birthDate=body["birthDate"], sex=body["gender"])
        return {"code": 0}

    monkeypatch.setattr(profile_sync, "update_personal_user_info", post_personal)

    result = sync_rider_settings(RiderSettingsSyncConfig("u", "p", "a", fields=None))

    assert personal_posts
    assert result.failed > 0
    assert result.field_statuses["ftp"] == "write_failed"
    assert result.field_statuses["height"] == "verified"


def test_sync_rider_settings_reports_readback_mismatch(monkeypatch):
    from intervalssync.igpsport import profile_sync

    sport, athlete = _rider_source()
    current = _rider_interval_destination()
    monkeypatch.setattr(profile_sync, "login", lambda *a, **k: {"Authorization": "Bearer x"})
    monkeypatch.setattr(profile_sync, "member_id_from_token", lambda *a, **k: 1)
    monkeypatch.setattr(profile_sync.intervals_icu, "fetch_sport_settings", lambda *a, **k: sport)
    monkeypatch.setattr(profile_sync.intervals_icu, "fetch_athlete_settings", lambda *a, **k: athlete)
    monkeypatch.setattr(profile_sync, "fetch_personal_interval_info", lambda *a, **k: copy.deepcopy(current))
    monkeypatch.setattr(profile_sync, "fetch_user_info", lambda *a, **k: _rider_user_destination())
    monkeypatch.setattr(profile_sync, "update_personal_interval_info", lambda *a, **k: {"code": 0})

    result = sync_rider_settings(
        RiderSettingsSyncConfig("u", "p", "a", fields="ftp")
    )

    assert result.updated == 1
    assert result.field_statuses == {"ftp": "verify_failed"}
    assert result.failed == 1


def test_interval_verifier_ignores_server_regenerated_zone_ids_only():
    expected = _rider_interval_destination()
    actual = copy.deepcopy(expected)
    for table_name in (
        "power",
        "heartRate",
        "heartRateReserve",
        "heartRateLactateThreshold",
    ):
        for row in actual[table_name]:
            row["id"] += 1000

    assert _verify_interval_state(actual, expected)

    actual["power"][0]["end"] += 1
    assert not _verify_interval_state(actual, expected)


def test_interval_verifier_detects_inactive_hr_table_changes():
    expected = _rider_interval_destination()
    actual = copy.deepcopy(expected)
    actual["heartRateReserve"][0]["end"] += 1

    assert not _verify_interval_state(actual, expected)


def test_sync_rider_settings_dry_run_can_show_values_without_writes(monkeypatch):
    from intervalssync.igpsport import profile_sync

    sport, athlete = _rider_source()
    monkeypatch.setattr(profile_sync, "login", lambda *a, **k: {"Authorization": "Bearer x"})
    monkeypatch.setattr(profile_sync, "member_id_from_token", lambda *a, **k: 1)
    monkeypatch.setattr(profile_sync.intervals_icu, "fetch_sport_settings", lambda *a, **k: sport)
    monkeypatch.setattr(profile_sync.intervals_icu, "fetch_athlete_settings", lambda *a, **k: athlete)
    monkeypatch.setattr(profile_sync, "fetch_personal_interval_info", lambda *a, **k: _rider_interval_destination())
    monkeypatch.setattr(profile_sync, "fetch_user_info", lambda *a, **k: _rider_user_destination())
    monkeypatch.setattr(profile_sync, "update_personal_interval_info", lambda *a, **k: pytest.fail("dry-run wrote interval group"))
    monkeypatch.setattr(profile_sync, "update_personal_user_info", lambda *a, **k: pytest.fail("dry-run wrote personal group"))

    result = sync_rider_settings(
        RiderSettingsSyncConfig(
            "u", "p", "a", fields="ftp", dry_run=True, show_values=True
        )
    )

    assert result.field_statuses == {"ftp": "would_update"}
    assert result.updated == 0
    assert result.source_values == {"ftp": 230}
    assert result.current_values == {"ftp": 220}
    assert result.desired_values == {"ftp": 230}


def test_sync_rider_settings_unchanged_second_run_posts_nothing(monkeypatch):
    from intervalssync.igpsport import profile_sync

    sport, athlete = _rider_source()
    current = _rider_interval_destination()
    current["member"]["ftp"] = 230
    monkeypatch.setattr(profile_sync, "login", lambda *a, **k: {"Authorization": "Bearer x"})
    monkeypatch.setattr(profile_sync, "member_id_from_token", lambda *a, **k: 1)
    monkeypatch.setattr(profile_sync.intervals_icu, "fetch_sport_settings", lambda *a, **k: sport)
    monkeypatch.setattr(profile_sync.intervals_icu, "fetch_athlete_settings", lambda *a, **k: athlete)
    monkeypatch.setattr(profile_sync, "fetch_personal_interval_info", lambda *a, **k: copy.deepcopy(current))
    monkeypatch.setattr(profile_sync, "fetch_user_info", lambda *a, **k: _rider_user_destination())
    monkeypatch.setattr(profile_sync, "update_personal_interval_info", lambda *a, **k: pytest.fail("unchanged field was written"))

    result = sync_rider_settings(
        RiderSettingsSyncConfig("u", "p", "a", fields="ftp")
    )

    assert result.field_statuses == {"ftp": "unchanged"}
    assert result.updated == 0
    assert result.failed == 0


def test_apply_intervals_settings_updates_thresholds_and_zones():
    settings = SportSettings(
        ftp=242,
        lthr=176,
        max_hr=193,
        power_zones=[55, 75, 90, 105, 120, 999],
        hr_zones=[120, 146, 166, 185, 193],
    )
    updated = apply_intervals_settings(_igpsport_payload(), settings)

    assert updated["member"]["ftp"] == 242
    assert updated["member"]["lthr"] == 176
    assert updated["member"]["mhr"] == 193
    assert updated["member"]["heartRateComputeMode"] == 0
    assert "weight" not in updated["member"]
    assert len(updated["power"]) == 7
    assert updated["power"][0]["end"] == 133
    assert updated["power"][-1]["end"] == 2500
    assert updated["power"][-2]["end"] <= 1999
    assert [zone["end"] for zone in updated["heartRate"]] == [120, 146, 166, 185, 193]


def test_apply_intervals_settings_keeps_other_member_fields():
    body = _igpsport_payload()
    settings = SportSettings(242, 176, 193, [55, 75, 90, 105, 120, 999], [120, 146, 166, 185, 193])
    updated = apply_intervals_settings(body, settings)
    assert updated["member"]["quietHeartRate"] == 60


def _ride_settings(**overrides: object) -> SportSettings:
    defaults = {
        "ftp": 242,
        "lthr": 176,
        "max_hr": 193,
        "power_zones": [55, 75, 90, 105, 120, 999],
        "hr_zones": [120, 146, 166, 185, 193],
    }
    defaults.update(overrides)
    return SportSettings(**defaults)


def test_compare_profile_thresholds_in_sync():
    body = apply_intervals_settings(_igpsport_payload(), _ride_settings())
    status = compare_profile_thresholds(
        body, _ride_settings(), weight=79.0, current_weight=79.0
    )
    assert status.needs_sync is False
    assert status.differences == []
    assert status.intervals_fingerprint == "242|176|193|79"


def test_compare_profile_thresholds_ftp_mismatch():
    status = compare_profile_thresholds(_igpsport_payload(), _ride_settings())
    assert status.needs_sync is True
    assert len(status.differences) == 3
    assert status.differences[0].startswith("FTP:")
    assert status.intervals_fingerprint == "242|176|193|"


def test_compare_profile_thresholds_lthr_mismatch_only():
    body = _igpsport_payload()
    body["member"]["ftp"] = 242
    body["member"]["mhr"] = 193
    status = compare_profile_thresholds(body, _ride_settings())
    assert status.needs_sync is True
    assert status.differences == ["LTHR: iGPSPORT 150 → intervals.icu 176"]


def test_compare_profile_thresholds_mhr_mismatch_only():
    body = _igpsport_payload()
    body["member"]["ftp"] = 242
    body["member"]["lthr"] = 176
    status = compare_profile_thresholds(body, _ride_settings())
    assert status.needs_sync is True
    assert status.differences == ["max HR: iGPSPORT 190 → intervals.icu 193"]


def test_build_personal_user_info_payload_maps_city_and_sex():
    from intervalssync.igpsport.interval_info import build_personal_user_info_payload

    payload = build_personal_user_info_payload(
        {
            "cityId": 103172,
            "cityName": "Braga",
            "sex": 1,
            "height": 179,
            "nickName": "Jorge Silva",
            "birthDate": "1998-08-17",
            "weight": 79.0,
            "ftp": 242,
            "avatar": "https://example.com/a.png",
        },
        76,
    )
    assert payload == {
        "areaId": 103172,
        "birthDate": "1998-08-17",
        "gender": 1,
        "height": 179,
        "nickName": "Jorge Silva",
        "weight": 76.0,
    }


def test_build_personal_user_info_payload_prefers_area_id_and_gender():
    from intervalssync.igpsport.interval_info import build_personal_user_info_payload

    payload = build_personal_user_info_payload(
        {
            "cityId": 0,
            "areaId": 1101172,
            "gender": 1,
            "sex": 0,
            "height": 179,
            "nickName": "Jorge",
            "birthDate": "1998-08-17",
        },
        76,
    )
    assert payload["areaId"] == 1101172
    assert payload["gender"] == 1
    assert payload["weight"] == 76.0


def test_update_user_weight_posts_personal_user_info(monkeypatch):
    from intervalssync.igpsport import interval_info

    posted: dict = {}

    class FakeResp:
        ok = True
        status_code = 200

        def json(self):
            return {"code": 0, "data": True}

    class FakeSession:
        def post(self, url, headers=None, json=None, timeout=None):
            posted["url"] = url
            posted["json"] = json
            return FakeResp()

    monkeypatch.setattr(
        interval_info,
        "fetch_user_info",
        lambda *a, **k: {
            "cityId": 103172,
            "cityName": "Braga",
            "sex": 1,
            "height": 179,
            "nickName": "Jorge Silva",
            "birthDate": "1998-08-17",
            "weight": 79.0,
        },
    )

    result = interval_info.update_user_weight(FakeSession(), {"Authorization": "Bearer x"}, 76)
    assert result["code"] == 0
    assert posted["url"].endswith("/User/UpdatePersonalUserInfo")
    assert posted["json"] == {
        "areaId": 103172,
        "birthDate": "1998-08-17",
        "gender": 1,
        "height": 179,
        "nickName": "Jorge Silva",
        "weight": 76.0,
    }


def test_interval_info_requests_use_bounded_connect_and_read_timeouts():
    from intervalssync.igpsport import interval_info

    calls = []

    class FakeResp:
        ok = True
        status_code = 200

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    class FakeSession:
        def get(self, url, **kwargs):
            calls.append(kwargs.get("timeout"))
            if url.endswith("UserIntervalInfo"):
                return FakeResp({"code": 0, "data": {"member": {}}})
            return FakeResp({"code": 0, "data": {}})

        def post(self, url, **kwargs):
            calls.append(kwargs.get("timeout"))
            return FakeResp({"code": 0, "data": {}})

    session = FakeSession()
    headers = {"Authorization": "Bearer x"}
    interval_info.fetch_personal_interval_info(session, headers)
    interval_info.update_personal_interval_info(session, headers, {})
    interval_info.fetch_user_info(session, headers)
    interval_info.update_personal_user_info(session, headers, {})

    assert calls == [(10, 30), (10, 30), (10, 30), (10, 30)]

    body = apply_intervals_settings(_igpsport_payload(), _ride_settings())
    status = compare_profile_thresholds(
        body, _ride_settings(), weight=76.1, current_weight=79.0
    )
    assert status.needs_sync is True
    assert status.differences == ["Weight: iGPSPORT 79 → intervals.icu 76"]
    assert status.intervals_fingerprint == "242|176|193|76"


def test_compare_profile_thresholds_weight_fractional_matches_after_round():
    body = apply_intervals_settings(_igpsport_payload(), _ride_settings())
    status = compare_profile_thresholds(
        body, _ride_settings(), weight=76.4, current_weight=76.0
    )
    assert status.needs_sync is False
    assert status.intervals_fingerprint == "242|176|193|76"


def test_compare_profile_thresholds_skips_weight_when_intervals_missing():
    body = apply_intervals_settings(_igpsport_payload(), _ride_settings())
    status = compare_profile_thresholds(
        body, _ride_settings(), weight=None, current_weight=79.0
    )
    assert status.needs_sync is False
    assert status.intervals_fingerprint == "242|176|193|"


def test_compare_profile_thresholds_skips_lthr_when_intervals_missing():
    body = _igpsport_payload()
    body["member"]["ftp"] = 242
    body["member"]["mhr"] = 193
    settings = _ride_settings(lthr=None)
    status = compare_profile_thresholds(body, settings)
    assert status.needs_sync is False
    assert status.intervals_fingerprint == "242||193|"


def test_fetch_profile_threshold_status(monkeypatch):
    from intervalssync.igpsport import profile_sync

    settings = _ride_settings()
    current = _igpsport_payload()

    monkeypatch.setattr(profile_sync, "login", lambda *a, **k: {"Authorization": "Bearer x"})
    monkeypatch.setattr(profile_sync, "member_id_from_token", lambda *a, **k: 1171353)
    monkeypatch.setattr(
        profile_sync.intervals_icu,
        "fetch_sport_settings",
        lambda *a, **k: settings,
    )
    monkeypatch.setattr(
        profile_sync.intervals_icu,
        "fetch_athlete_weight",
        lambda *a, **k: 76.1,
    )
    monkeypatch.setattr(
        profile_sync,
        "fetch_personal_interval_info",
        lambda *a, **k: current,
    )
    monkeypatch.setattr(
        profile_sync,
        "fetch_user_info",
        lambda *a, **k: {"weight": 79.0},
    )

    status = profile_sync.fetch_profile_threshold_status(
        ProfileSyncConfig("user", "pass", "api-key"),
    )
    assert status.needs_sync is True
    assert any(diff.startswith("FTP:") for diff in status.differences)
    assert any(diff.startswith("Weight:") for diff in status.differences)


def test_sync_profile_zones_end_to_end(monkeypatch):
    from intervalssync.igpsport import profile_sync

    posted: dict = {}
    weight_posts: list[int] = []

    settings = SportSettings(
        ftp=242,
        lthr=176,
        max_hr=193,
        power_zones=[55, 75, 90, 105, 120, 999],
        hr_zones=[120, 146, 166, 185, 193],
    )
    current = _igpsport_payload()

    monkeypatch.setattr(profile_sync, "login", lambda *a, **k: {"Authorization": "Bearer x"})
    monkeypatch.setattr(profile_sync, "member_id_from_token", lambda *a, **k: 1171353)
    monkeypatch.setattr(
        profile_sync.intervals_icu,
        "fetch_sport_settings",
        lambda *a, **k: settings,
    )
    monkeypatch.setattr(
        profile_sync.intervals_icu,
        "fetch_athlete_weight",
        lambda *a, **k: 76.1,
    )

    calls = {"get": 0}
    userinfo_weight = {"value": 79.0}

    def fake_fetch(session, headers, *args, **kwargs):
        calls["get"] += 1
        return current if calls["get"] == 1 else apply_intervals_settings(current, settings)

    def fake_user_info(session, headers, *args, **kwargs):
        return {"weight": userinfo_weight["value"]}

    def fake_update(session, headers, body, *args, **kwargs):
        posted["body"] = body
        return {"code": 0}

    def fake_update_weight(session, headers, weight_kg, *args, **kwargs):
        weight_posts.append(weight_kg)
        userinfo_weight["value"] = float(weight_kg)
        return {"code": 0}

    monkeypatch.setattr(profile_sync, "fetch_personal_interval_info", fake_fetch)
    monkeypatch.setattr(profile_sync, "fetch_user_info", fake_user_info)
    monkeypatch.setattr(profile_sync, "update_personal_interval_info", fake_update)
    monkeypatch.setattr(profile_sync, "update_user_weight", fake_update_weight)

    result = profile_sync.sync_profile_zones(
        ProfileSyncConfig("user", "pass", "api-key"),
        progress=lambda _message: None,
    )

    assert posted["body"]["member"]["ftp"] == 242
    assert "weight" not in posted["body"]["member"] or posted["body"]["member"].get("weight") != 76.0
    assert weight_posts == [76]
    assert result.after is not None
    assert result.after["member"]["mhr"] == 193
    assert result.weight_before == 79.0
    assert result.weight_after == 76.0


def test_sync_profile_zones_skips_weight_update_when_unchanged(monkeypatch):
    from intervalssync.igpsport import profile_sync

    settings = _ride_settings()
    current = apply_intervals_settings(_igpsport_payload(), settings)
    weight_posts: list[int] = []

    monkeypatch.setattr(profile_sync, "login", lambda *a, **k: {"Authorization": "Bearer x"})
    monkeypatch.setattr(profile_sync, "member_id_from_token", lambda *a, **k: 1171353)
    monkeypatch.setattr(
        profile_sync.intervals_icu,
        "fetch_sport_settings",
        lambda *a, **k: settings,
    )
    monkeypatch.setattr(
        profile_sync.intervals_icu,
        "fetch_athlete_weight",
        lambda *a, **k: 76.0,
    )
    monkeypatch.setattr(
        profile_sync,
        "fetch_personal_interval_info",
        lambda *a, **k: current,
    )
    monkeypatch.setattr(
        profile_sync,
        "fetch_user_info",
        lambda *a, **k: {"weight": 76.0, "cityId": 103172, "cityName": "Braga"},
    )
    monkeypatch.setattr(
        profile_sync,
        "update_personal_interval_info",
        lambda *a, **k: {"code": 0},
    )
    monkeypatch.setattr(
        profile_sync,
        "update_user_weight",
        lambda *a, **k: weight_posts.append(a[2]),
    )

    result = profile_sync.sync_profile_zones(
        ProfileSyncConfig("user", "pass", "api-key"),
        progress=lambda _message: None,
    )
    assert weight_posts == []
    assert result.weight_after == 76.0
