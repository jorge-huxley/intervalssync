"""Tests for Bryton regional endpoint selection."""

from __future__ import annotations

import pytest

from intervalssync.bryton import core, workout
from intervalssync.bryton.ddp import BrytonSession
from intervalssync.bryton.exceptions import BrytonSyncError
from intervalssync.bryton.region import CHINA, INTERNATIONAL, resolve_region


def test_resolve_region_defaults_to_international():
    assert resolve_region(None) is INTERNATIONAL
    assert resolve_region("") is INTERNATIONAL
    assert resolve_region("international") is INTERNATIONAL


def test_resolve_region_china():
    assert resolve_region("china") is CHINA
    assert CHINA.host == "active.cn.brytonactive.com"
    assert CHINA.web_host == "active.cn.brytonactive.com"


def test_resolve_region_rejects_unknown_name():
    with pytest.raises(ValueError, match="Unknown Bryton region"):
        resolve_region("eu")


def test_sync_logs_in_to_china_host(monkeypatch, tmp_path):
    captured: dict[str, str] = {}

    def fake_login(email, password, *, host):
        captured["host"] = host
        return BrytonSession(user_id="u1", auth_token="tok", host=host)

    monkeypatch.setattr(core, "login", fake_login)
    monkeypatch.setattr(core, "list_activities", lambda *a, **k: [])

    cfg = core.SyncConfig(
        bryton_email="a@b.com",
        bryton_password="pw",
        intervals_api_key="key",
        bryton_region="china",
        download_dir=tmp_path,
        list_activities=False,
        download_fit=False,
        upload_intervals=False,
    )
    core.sync(cfg)

    assert captured["host"] == CHINA.host


def test_sync_rejects_unknown_region(tmp_path):
    cfg = core.SyncConfig(
        bryton_email="a@b.com",
        bryton_password="pw",
        intervals_api_key="key",
        bryton_region="eu",
        download_dir=tmp_path,
    )
    with pytest.raises(BrytonSyncError, match="Unknown Bryton region"):
        core.sync(cfg)


def test_workout_upload_uses_china_web_host(monkeypatch):
    captured: dict[str, str] = {}

    def fake_web_login(email, password, *, host=None):
        captured["host"] = host or ""
        raise BrytonSyncError("stop before network")

    monkeypatch.setattr(workout, "web_login", fake_web_login)
    cfg = workout.BrytonWorkoutUploadConfig(
        bryton_email="a@b.com",
        bryton_password="pw",
        intervals_api_key="key",
        bryton_region="china",
    )

    with pytest.raises(BrytonSyncError, match="stop before network"):
        workout.upload_workouts(cfg)

    assert captured["host"] == CHINA.web_host
