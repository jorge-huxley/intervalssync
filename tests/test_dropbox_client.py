"""Tests for Dropbox helper behavior. No live Dropbox calls are made."""

from __future__ import annotations

from igpsync.dropbox_client import dropbox_path_for


def test_dropbox_path_uses_app_folder_subdirectory():
    assert dropbox_path_for("/igpsport-fit", 123) == "/igpsport-fit/igpsport_123.fit"


def test_dropbox_path_normalizes_folder():
    assert dropbox_path_for("rides/", 7) == "/rides/igpsport_7.fit"
