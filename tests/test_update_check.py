"""Tests for the GitHub release update check (offline; requests is faked)."""

from __future__ import annotations

from igpsync import update_check


class FakeResponse:
    def __init__(self, *, status=200, json_data=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._json = json_data

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self.ok:
            raise update_check.requests.HTTPError(f"HTTP {self.status_code}")


def _fake_latest(tag):
    return lambda *a, **k: FakeResponse(json_data={"tag_name": tag})


def test_newer_release_returns_version(monkeypatch):
    monkeypatch.setattr(update_check.requests, "get", _fake_latest("v0.3.0"))
    assert update_check.check_for_update("0.2.0") == "0.3.0"


def test_same_version_returns_none(monkeypatch):
    monkeypatch.setattr(update_check.requests, "get", _fake_latest("v0.2.0"))
    assert update_check.check_for_update("0.2.0") is None


def test_older_release_returns_none(monkeypatch):
    monkeypatch.setattr(update_check.requests, "get", _fake_latest("v0.1.0"))
    assert update_check.check_for_update("0.2.0") is None


def test_dev_build_skips_check(monkeypatch):
    # Should not even hit the network for a dev/local build.
    def boom(*a, **k):
        raise AssertionError("network should not be called for dev builds")

    monkeypatch.setattr(update_check.requests, "get", boom)
    assert update_check.check_for_update("0.0.0+dev") is None


def test_network_error_returns_none(monkeypatch):
    def boom(*a, **k):
        raise update_check.requests.ConnectionError("offline")

    monkeypatch.setattr(update_check.requests, "get", boom)
    assert update_check.check_for_update("0.2.0") is None
