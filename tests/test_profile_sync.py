"""Tests for intervals.icu → iGPSPORT profile sync orchestration."""

from __future__ import annotations

from intervalssync.igpsport.profile_sync import (
    ProfileSyncConfig,
    apply_intervals_settings,
)
from intervalssync.intervals_icu import SportSettings


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


def test_sync_profile_zones_end_to_end(monkeypatch):
    from intervalssync.igpsport import profile_sync

    posted: dict = {}

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

    calls = {"get": 0}

    def fake_fetch(session, headers):
        calls["get"] += 1
        return current if calls["get"] == 1 else apply_intervals_settings(current, settings)

    def fake_update(session, headers, body):
        posted["body"] = body
        return {"code": 0}

    monkeypatch.setattr(profile_sync, "fetch_personal_interval_info", fake_fetch)
    monkeypatch.setattr(profile_sync, "update_personal_interval_info", fake_update)

    result = profile_sync.sync_profile_zones(
        ProfileSyncConfig("user", "pass", "api-key"),
        progress=lambda _message: None,
    )

    assert posted["body"]["member"]["ftp"] == 242
    assert result.after is not None
    assert result.after["member"]["mhr"] == 193
