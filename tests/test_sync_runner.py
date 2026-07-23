"""Tests for the shared GUI activity sync runner."""

from __future__ import annotations

from intervalssync.gui import config as config_module
from intervalssync.gui import sync_runner


def test_try_begin_sync_is_exclusive():
    assert sync_runner.try_begin_sync() is True
    try:
        assert sync_runner.try_begin_sync() is False
    finally:
        sync_runner.end_sync()
    assert sync_runner.try_begin_sync() is True
    sync_runner.end_sync()


def test_run_enabled_activity_sync_reports_busy(monkeypatch):
    assert sync_runner.try_begin_sync() is True
    try:
        outcome = sync_runner.run_enabled_activity_sync(
            config_module.AppConfig(enable_igpsport=False, enable_bryton=False),
            igp_password=None,
            bryton_password=None,
            api_key=None,
            dropbox_refresh_token=None,
        )
        assert outcome.busy is True
    finally:
        sync_runner.end_sync()


def test_run_enabled_activity_sync_igpsport(monkeypatch):
    calls: list[str] = []

    class FakeResult:
        uploaded = 2
        uploaded_dropbox = 0
        skipped = 1
        failed = 0

    def fake_sync(config, progress=None):
        calls.append(config.igp_user)
        if progress:
            progress("ok")
        return FakeResult()

    monkeypatch.setattr(sync_runner, "igpsport_sync", fake_sync)

    outcome = sync_runner.run_enabled_activity_sync(
        config_module.AppConfig(
            enable_igpsport=True,
            enable_bryton=False,
            igp_user="me@example.com",
        ),
        igp_password="secret",
        bryton_password=None,
        api_key="key",
        dropbox_refresh_token=None,
    )
    assert outcome.busy is False
    assert outcome.uploaded == 2
    assert outcome.skipped == 1
    assert calls == ["me@example.com"]
    # Lock must be released for subsequent runs.
    assert sync_runner.try_begin_sync() is True
    sync_runner.end_sync()
