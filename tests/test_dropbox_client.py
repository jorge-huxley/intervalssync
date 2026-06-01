"""Tests for Dropbox helper behavior. No live Dropbox calls are made."""

from __future__ import annotations

import types

from dropbox.exceptions import ApiError
from dropbox.files import FileMetadata, FolderMetadata, ListFolderError
from dropbox.files import LookupError as DbxLookupError

from igpsync import dropbox_client
from igpsync.dropbox_client import dropbox_path_for, list_dropbox_ride_ids


def test_dropbox_path_uses_app_folder_subdirectory():
    assert dropbox_path_for("/igpsport-fit", 123) == "/igpsport-fit/igpsport_123.fit"


def test_dropbox_path_normalizes_folder():
    assert dropbox_path_for("rides/", 7) == "/rides/igpsport_7.fit"


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


def test_list_dropbox_ride_ids_parses_fit_names(monkeypatch):
    entries = [
        FileMetadata(name="igpsport_1.fit"),
        FileMetadata(name="igpsport_42.fit"),
        FileMetadata(name="notes.txt"),  # ignored — wrong name
        FolderMetadata(name="subfolder"),  # ignored — not a file
    ]
    monkeypatch.setattr(
        dropbox_client.dropbox, "Dropbox", lambda **kw: _FakeDbx([_page(entries)])
    )
    assert list_dropbox_ride_ids("/igpsport-fit", "token", "key") == {1, 42}


def test_list_dropbox_ride_ids_follows_pagination(monkeypatch):
    pages = [
        _page([FileMetadata(name="igpsport_1.fit")], has_more=True, cursor="c"),
        _page([FileMetadata(name="igpsport_2.fit")]),
    ]
    monkeypatch.setattr(
        dropbox_client.dropbox, "Dropbox", lambda **kw: _FakeDbx(pages)
    )
    assert list_dropbox_ride_ids("/igpsport-fit", "token", "key") == {1, 2}


def test_list_dropbox_ride_ids_returns_empty_when_folder_missing(monkeypatch):
    not_found = ApiError(
        "rid", ListFolderError.path(DbxLookupError.not_found), "", ""
    )

    class _MissingDbx(_FakeDbx):
        def files_list_folder(self, path):
            raise not_found

    monkeypatch.setattr(
        dropbox_client.dropbox, "Dropbox", lambda **kw: _MissingDbx([])
    )
    assert list_dropbox_ride_ids("/igpsport-fit", "token", "key") == set()
