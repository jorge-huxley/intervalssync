"""Tests for Bryton sync orchestration."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from intervalssync.bryton import core
from intervalssync.bryton.ddp import BrytonSession, _is_deleted_activity


def _local_ts(year: int, month: int, day: int, hour: int, minute: int, second: int) -> int:
    return int(datetime(year, month, day, hour, minute, second).timestamp())


def _compact_fit_name(
    year: int, month: int, day: int, hour: int, minute: int, second: int
) -> str:
    return datetime(year, month, day, hour, minute, second).strftime("%y%m%d%H%M%S") + ".fit"


def test_external_id_for():
    assert core.external_id_for("abc123") == "bryton_abc123"


def test_dropbox_filename_for_start_time():
    ts = _local_ts(2026, 5, 30, 5, 27, 24)
    act = core.Activity("act1", "Ride", ts)
    assert core.dropbox_filename_for(act) == "260530052724.fit"


def test_dropbox_filename_uses_default_when_date_disabled():
    ts = _local_ts(2026, 5, 30, 5, 27, 24)
    act = core.Activity("act1", "Ride", ts)
    assert core.dropbox_filename_for(act, use_date=False) == "bryton_act1.fit"


def test_dropbox_filename_falls_back_for_zero_timestamp():
    act = core.Activity("act1", "Ride", 0)
    assert core.dropbox_filename_for(act) == "bryton_act1.fit"


@pytest.mark.parametrize(
    "fields,deleted",
    [
        ({"name": "Morning ride", "local_start_time": 1}, False),
        ({"_deleted": True, "name": "Ride"}, True),
        ({"name": "_deleted", "local_start_time": 0}, True),
    ],
)
def test_is_deleted_activity(fields, deleted):
    assert _is_deleted_activity(fields) is deleted


@pytest.fixture
def stub_sync(monkeypatch, tmp_path):
    """Replace every network leaf so sync() runs offline. Returns a recorder."""
    rec = {
        "downloaded": [],
        "uploaded": [],
        "dropbox": [],
        "existing": set(),
        "dropbox_existing": set(),
        "dropbox_ok": True,
    }

    activities = [
        {
            "_id": "act1",
            "name": "Ride 1",
            "local_start_time": _local_ts(2026, 5, 28, 19, 20, 42),
        },
        {
            "_id": "act2",
            "name": "Ride 2",
            "local_start_time": _local_ts(2026, 5, 26, 18, 47, 6),
        },
        {
            "_id": "act3",
            "name": "Ride 3",
            "local_start_time": _local_ts(2026, 5, 24, 8, 27, 17),
        },
    ]

    monkeypatch.setattr(core, "login", lambda *a, **k: BrytonSession(user_id="u1", auth_token="tok"))

    def fake_download(activity_id, sess, dest_path, **kwargs):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"\x00" * 12 + b".FIT" + b"\x00" * 4)
        rec["downloaded"].append(dest_path.name)
        return dest_path

    monkeypatch.setattr(core, "list_activities", lambda *a, **k: activities)
    monkeypatch.setattr(core, "download_fit_to_path", fake_download)
    monkeypatch.setattr(
        core, "fetch_uploaded_external_ids", lambda k, o, n: rec["existing"]
    )

    def fake_upload(fp, title, ext, key):
        rec["uploaded"].append(ext)
        return "icu-1"

    monkeypatch.setattr(core, "upload_fit_file", fake_upload)

    def fake_dropbox(fp, filename, token, app_key, folder):
        rec["dropbox"].append((filename, token, app_key, folder, fp.name))
        if not rec["dropbox_ok"]:
            raise RuntimeError("dropbox upload failed")

    monkeypatch.setattr(core, "upload_to_dropbox", fake_dropbox)
    monkeypatch.setattr(
        core,
        "list_dropbox_fit_names",
        lambda folder, token, app_key: set(rec["dropbox_existing"]),
    )

    rec["tmp"] = tmp_path
    return rec


def _config(tmp_path, **overrides):
    base = dict(
        bryton_email="a@b.com",
        bryton_password="pw",
        intervals_api_key="key",
        dropbox_refresh_token="dbx-refresh",
        dropbox_app_key="dbx-app",
        download_dir=tmp_path,
        delete_after_upload=False,
        force_resync=False,
        activity_type="",
        list_activities=False,
        download_fit=True,
        upload_intervals=True,
        upload_dropbox=False,
        dropbox_folder="/intervalssync-fit",
        dropbox_date_filenames=True,
    )
    base.update(overrides)
    return core.SyncConfig(**base)


def test_sync_ignores_deleted_activities(monkeypatch, tmp_path):
    session = BrytonSession(user_id="u1", auth_token="tok")
    activities = [
        {"_id": "gone", "name": "_deleted", "local_start_time": 0},
        {"_id": "act2", "name": "Morning ride", "local_start_time": 1_700_000_000},
    ]

    monkeypatch.setattr(core, "login", lambda *a, **k: session)
    monkeypatch.setattr(core, "list_activities", lambda *a, **k: [activities[1]])
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
    )
    result = core.sync(cfg)
    assert result.listed == 1
    assert result.downloaded == 1
    assert result.failed == 0


def test_sync_skips_already_uploaded(stub_sync):
    stub_sync["existing"] = {"bryton_act1", "bryton_act2"}
    result = core.sync(_config(stub_sync["tmp"]))
    assert result.skipped == 2
    assert result.uploaded == 1
    assert stub_sync["downloaded"] == ["bryton_act3.fit"]


def test_sync_downloads_and_uploads(stub_sync):
    result = core.sync(_config(stub_sync["tmp"], delete_after_upload=True))
    assert result.downloaded == 3
    assert result.uploaded == 3
    assert not (stub_sync["tmp"] / "bryton_act1.fit").exists()


def test_activity_date_range_from_timestamps():
    acts = [
        core.Activity("a", "t", 1_715_000_000),
        core.Activity("b", "t", 1_716_000_000),
    ]
    oldest, newest = core._activity_date_range(acts)
    assert isinstance(oldest, date)
    assert newest >= oldest


def test_sync_does_not_upload_to_dropbox_when_disabled(stub_sync):
    core.sync(_config(stub_sync["tmp"], upload_dropbox=False))
    assert stub_sync["dropbox"] == []


def test_sync_uploads_to_dropbox_after_intervals(stub_sync):
    result = core.sync(_config(stub_sync["tmp"], upload_dropbox=True))
    assert result.uploaded == 3
    assert result.uploaded_dropbox == 3
    assert [item[0] for item in stub_sync["dropbox"]] == [
        _compact_fit_name(2026, 5, 28, 19, 20, 42),
        _compact_fit_name(2026, 5, 26, 18, 47, 6),
        _compact_fit_name(2026, 5, 24, 8, 27, 17),
    ]
    assert stub_sync["dropbox"][0][1:4] == ("dbx-refresh", "dbx-app", "/intervalssync-fit")
    assert stub_sync["dropbox"][0][4] == "bryton_act1.fit"


def test_sync_uploads_to_dropbox_even_when_intervals_skips(stub_sync):
    stub_sync["existing"] = {"bryton_act1", "bryton_act2"}
    result = core.sync(_config(stub_sync["tmp"], upload_dropbox=True))
    assert result.skipped == 2
    assert result.uploaded == 1
    assert result.uploaded_dropbox == 3
    assert [item[0] for item in stub_sync["dropbox"]] == [
        _compact_fit_name(2026, 5, 28, 19, 20, 42),
        _compact_fit_name(2026, 5, 26, 18, 47, 6),
        _compact_fit_name(2026, 5, 24, 8, 27, 17),
    ]


def test_sync_uploads_to_dropbox_when_intervals_disabled(stub_sync):
    result = core.sync(
        _config(stub_sync["tmp"], upload_intervals=False, upload_dropbox=True)
    )
    assert result.uploaded == 0
    assert stub_sync["uploaded"] == []
    assert result.uploaded_dropbox == 3
    assert [item[0] for item in stub_sync["dropbox"]] == [
        _compact_fit_name(2026, 5, 28, 19, 20, 42),
        _compact_fit_name(2026, 5, 26, 18, 47, 6),
        _compact_fit_name(2026, 5, 24, 8, 27, 17),
    ]


def test_sync_uploads_to_dropbox_with_default_filenames_when_configured(stub_sync):
    result = core.sync(
        _config(
            stub_sync["tmp"],
            upload_intervals=False,
            upload_dropbox=True,
            dropbox_date_filenames=False,
        )
    )
    assert result.uploaded_dropbox == 3
    assert [item[0] for item in stub_sync["dropbox"]] == [
        "bryton_act1.fit",
        "bryton_act2.fit",
        "bryton_act3.fit",
    ]


def test_sync_skips_dropbox_for_existing_files(stub_sync):
    stub_sync["dropbox_existing"] = {
        _compact_fit_name(2026, 5, 28, 19, 20, 42),
        _compact_fit_name(2026, 5, 26, 18, 47, 6),
    }
    result = core.sync(
        _config(stub_sync["tmp"], upload_intervals=False, upload_dropbox=True)
    )
    assert result.skipped_dropbox == 2
    assert result.uploaded_dropbox == 1
    assert [item[0] for item in stub_sync["dropbox"]] == [
        _compact_fit_name(2026, 5, 24, 8, 27, 17)
    ]


def test_sync_keeps_file_when_dropbox_upload_fails(stub_sync):
    stub_sync["dropbox_ok"] = False
    result = core.sync(
        _config(stub_sync["tmp"], delete_after_upload=True, upload_dropbox=True)
    )
    assert result.uploaded == 3
    assert result.failed_dropbox == 3
    assert (stub_sync["tmp"] / "bryton_act1.fit").exists()


def test_sync_deletes_file_after_intervals_and_dropbox_when_enabled(stub_sync):
    result = core.sync(
        _config(stub_sync["tmp"], delete_after_upload=True, upload_dropbox=True)
    )
    assert result.uploaded_dropbox == 3
    assert not (stub_sync["tmp"] / "bryton_act1.fit").exists()


def test_sync_requires_dropbox_app_key_when_enabled(stub_sync):
    with pytest.raises(core.BrytonSyncError, match="Dropbox app key"):
        core.sync(
            _config(
                stub_sync["tmp"],
                upload_dropbox=True,
                dropbox_app_key=None,
            )
        )


def test_sync_requires_dropbox_connection_when_enabled(stub_sync):
    with pytest.raises(core.BrytonSyncError, match="Connect Dropbox"):
        core.sync(
            _config(
                stub_sync["tmp"],
                upload_dropbox=True,
                dropbox_refresh_token=None,
            )
        )
