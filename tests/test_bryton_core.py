"""Tests for Bryton sync orchestration."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from intervalssync.bryton import core
from intervalssync.bryton.ddp import BrytonSession


def test_external_id_for():
    assert core.external_id_for("abc123") == "bryton_abc123"


def test_sync_skips_already_uploaded(monkeypatch, tmp_path):
    session = BrytonSession(user_id="u1", auth_token="tok")
    activities = [{"_id": "act1", "name": "Ride", "local_start_time": 1_700_000_000}]

    monkeypatch.setattr(core, "login", lambda *a, **k: session)
    monkeypatch.setattr(core, "list_activities", lambda *a, **k: activities)
    monkeypatch.setattr(
        core,
        "fetch_uploaded_external_ids",
        lambda *a, **k: {"bryton_act1"},
    )
    monkeypatch.setattr(core, "download_fit_to_path", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not download")))

    cfg = core.SyncConfig(
        bryton_email="a@b.com",
        bryton_password="pw",
        intervals_api_key="key",
        download_dir=tmp_path,
    )
    result = core.sync(cfg)
    assert result.skipped == 1
    assert result.downloaded == 0


def test_sync_downloads_and_uploads(monkeypatch, tmp_path):
    session = BrytonSession(user_id="u1", auth_token="tok")
    activities = [{"_id": "act2", "name": "Morning ride", "local_start_time": 1_700_000_000}]

    monkeypatch.setattr(core, "login", lambda *a, **k: session)
    monkeypatch.setattr(core, "list_activities", lambda *a, **k: activities)
    monkeypatch.setattr(core, "fetch_uploaded_external_ids", lambda *a, **k: set())

    def fake_download(activity_id, sess, dest_path, **kwargs):
        dest_path.write_bytes(b"\x00" * 12 + b".FIT" + b"\x00" * 4)
        return dest_path

    monkeypatch.setattr(core, "download_fit_to_path", fake_download)
    monkeypatch.setattr(core, "upload_fit_file", lambda *a, **k: "icu-1")

    cfg = core.SyncConfig(
        bryton_email="a@b.com",
        bryton_password="pw",
        intervals_api_key="key",
        download_dir=tmp_path,
        delete_after_upload=True,
    )
    result = core.sync(cfg)
    assert result.downloaded == 1
    assert result.uploaded == 1
    assert not (tmp_path / "bryton_act2.fit").exists()


def test_activity_date_range_from_timestamps():
    acts = [
        core.Activity("a", "t", 1_715_000_000),
        core.Activity("b", "t", 1_716_000_000),
    ]
    oldest, newest = core._activity_date_range(acts)
    assert isinstance(oldest, date)
    assert newest >= oldest
