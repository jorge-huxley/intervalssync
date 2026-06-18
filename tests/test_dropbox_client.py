"""Tests for Dropbox helper behavior. No live Dropbox calls are made."""

from __future__ import annotations

import types

import pytest
from dropbox.exceptions import ApiError
from dropbox.files import FileMetadata, FolderMetadata, ListFolderError
from dropbox.files import LookupError as DbxLookupError
from requests.exceptions import HTTPError

from intervalssync import dropbox_client
from intervalssync.dropbox_client import (
    dropbox_path_for,
    finish_dropbox_auth,
    list_dropbox_fit_names,
)


def test_dropbox_path_uses_app_folder_subdirectory():
    filename = "ride-0-2026-06-03-17-23-53.fit"
    assert dropbox_path_for("/Fit files", filename) == f"/Fit files/{filename}"


def test_dropbox_path_normalizes_folder():
    assert dropbox_path_for("rides/", "igpsport_7.fit") == "/rides/igpsport_7.fit"


class _FakeDbx:
    """Minimal stand-in for dropbox.Dropbox used as a context manager."""

    def __init__(self, pages):
        self._pages = pages
        self._i = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def files_list_folder(self, path):
        return self._pages[0]

    def files_list_folder_continue(self, cursor):
        self._i += 1
        return self._pages[self._i]


def _page(entries, has_more=False, cursor=""):
    return types.SimpleNamespace(entries=entries, has_more=has_more, cursor=cursor)


def test_list_dropbox_fit_names_returns_fit_files(monkeypatch):
    entries = [
        FileMetadata(name="igpsport_1.fit"),
        FileMetadata(name="ride-0-2026-06-03-17-23-53.fit"),
        FileMetadata(name="notes.txt"),  # ignored — wrong name
        FolderMetadata(name="subfolder"),  # ignored — not a file
    ]
    monkeypatch.setattr(
        dropbox_client.dropbox, "Dropbox", lambda **kw: _FakeDbx([_page(entries)])
    )
    assert list_dropbox_fit_names("/intervalssync-fit", "token", "key") == {
        "igpsport_1.fit",
        "ride-0-2026-06-03-17-23-53.fit",
    }


def test_list_dropbox_fit_names_follows_pagination(monkeypatch):
    pages = [
        _page([FileMetadata(name="igpsport_1.fit")], has_more=True, cursor="c"),
        _page([FileMetadata(name="ride-0-2026-06-03-17-23-53.fit")]),
    ]
    monkeypatch.setattr(
        dropbox_client.dropbox, "Dropbox", lambda **kw: _FakeDbx(pages)
    )
    assert list_dropbox_fit_names("/intervalssync-fit", "token", "key") == {
        "igpsport_1.fit",
        "ride-0-2026-06-03-17-23-53.fit",
    }


def test_list_dropbox_fit_names_returns_empty_when_folder_missing(monkeypatch):
    not_found = ApiError(
        "rid", ListFolderError.path(DbxLookupError.not_found), "", ""
    )

    class _MissingDbx(_FakeDbx):
        def files_list_folder(self, path):
            raise not_found

    monkeypatch.setattr(
        dropbox_client.dropbox, "Dropbox", lambda **kw: _MissingDbx([])
    )
    assert list_dropbox_fit_names("/intervalssync-fit", "token", "key") == set()


class _FailingFlow:
    """Stands in for the OAuth flow; finish() raises a token-exchange error."""

    def __init__(self, body):
        self._body = body

    def finish(self, code):
        resp = types.SimpleNamespace(text=self._body)
        raise HTTPError("400 Client Error: Bad Request", response=resp)


def test_finish_dropbox_auth_friendly_message_for_expired_code():
    flow = _FailingFlow('{"error": "invalid_grant", "error_description": "..."}')
    with pytest.raises(RuntimeError, match="expired or was already used"):
        finish_dropbox_auth(flow, "somecode")


def test_finish_dropbox_auth_falls_back_to_raw_error():
    flow = _FailingFlow('{"error": "invalid_client"}')
    with pytest.raises(RuntimeError, match="invalid_client"):
        finish_dropbox_auth(flow, "somecode")
