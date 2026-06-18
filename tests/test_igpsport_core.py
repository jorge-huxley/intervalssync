"""Tests for the pure sync logic in intervalssync.igpsport.core.

Network calls are stubbed so nothing hits iGPSPORT or intervals.icu. The leaf
HTTP helpers are tested by faking `requests`; the `sync` orchestrator is tested
by replacing the leaf helpers it calls.
"""

from __future__ import annotations

from datetime import date

import pytest

from intervalssync.igpsport import core
from intervalssync import intervals_icu


class FakeResponse:
    def __init__(self, *, status=200, json_data=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._json = json_data

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self.ok:
            raise core.requests.HTTPError(f"HTTP {self.status_code}")


# --------------------------------------------------------------------------- #
# Leaf helpers
# --------------------------------------------------------------------------- #

def test_external_id_for():
    assert core.external_id_for(123) == "igpsport_123"


def test_dropbox_filename_for_start_time():
    act = core.Activity(1, "Ride", "2026-06-03 17:23:53")
    assert core.dropbox_filename_for(act) == "ride-0-2026-06-03-17-23-53.fit"


def test_dropbox_filename_uses_default_name_when_date_disabled():
    act = core.Activity(1, "Ride", "2026-06-03 17:23:53")
    assert core.dropbox_filename_for(act, use_date=False) == "igpsport_1.fit"


def test_dropbox_filename_falls_back_to_external_id_for_bad_start_time():
    act = core.Activity(1, "Ride", "unknown date")
    assert core.dropbox_filename_for(act) == "igpsport_1.fit"


def test_activity_date_range_from_start_times():
    acts = [
        core.Activity(1, "a", "2026-05-20 10:00:00"),
        core.Activity(2, "b", "2026-05-28 19:20:42"),
    ]
    oldest, newest = core._activity_date_range(acts)
    assert oldest == date(2026, 5, 19)  # min - 1 day
    assert newest == date(2026, 5, 29)  # max + 1 day


def test_activity_date_range_fallback_when_unparseable():
    acts = [core.Activity(1, "a", "unknown date")]
    oldest, newest = core._activity_date_range(acts)
    assert (newest - oldest).days >= 365


def test_upload_returns_activity_id_from_activities(monkeypatch, tmp_path):
    fit = tmp_path / "igpsport_1.fit"
    fit.write_bytes(b"FIT")
    monkeypatch.setattr(
        intervals_icu.requests,
        "post",
        lambda *a, **k: FakeResponse(json_data={"id": "iX", "activities": [{"id": "i999"}]}),
    )
    assert core.upload_to_intervals(fit, "Ride", 1, "key") == "i999"


def test_upload_falls_back_to_top_level_id(monkeypatch, tmp_path):
    fit = tmp_path / "igpsport_1.fit"
    fit.write_bytes(b"FIT")
    monkeypatch.setattr(
        intervals_icu.requests,
        "post",
        lambda *a, **k: FakeResponse(json_data={"id": "iTOP", "activities": []}),
    )
    assert core.upload_to_intervals(fit, "Ride", 1, "key") == "iTOP"


def test_upload_returns_none_on_failure(monkeypatch, tmp_path):
    fit = tmp_path / "igpsport_1.fit"
    fit.write_bytes(b"FIT")
    monkeypatch.setattr(intervals_icu.requests, "post", lambda *a, **k: FakeResponse(status=500))
    assert core.upload_to_intervals(fit, "Ride", 1, "key") is None


def test_fetch_uploaded_external_ids_filters_empty(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests,
        "get",
        lambda *a, **k: FakeResponse(
            json_data=[
                {"external_id": "igpsport_1"},
                {"external_id": None},
                {},
                {"external_id": "igpsport_2"},
            ]
        ),
    )
    ids = core.fetch_uploaded_external_ids("key", date(2026, 1, 1), date(2026, 1, 2))
    assert ids == {"igpsport_1", "igpsport_2"}


@pytest.mark.parametrize("status,expected", [(200, True), (400, False)])
def test_set_activity_type(monkeypatch, status, expected):
    monkeypatch.setattr(intervals_icu.requests, "put", lambda *a, **k: FakeResponse(status=status))
    assert core.set_activity_type("i1", "MountainBikeRide", "key") is expected


def test_login_builds_bearer_from_cookie(monkeypatch):
    class FakeCookies:
        def get(self, name):
            return "abc%20def" if name == "loginToken" else None

    class FakeSession:
        cookies = FakeCookies()

        def post(self, *a, **k):
            return FakeResponse(status=200)

    headers = core.login(FakeSession(), "user", "pass")
    assert headers == {"Authorization": "Bearer abc def"}  # %20 -> space


def test_login_raises_without_cookie(monkeypatch):
    class FakeSession:
        cookies = type("C", (), {"get": lambda self, n: None})()

        def post(self, *a, **k):
            return FakeResponse(status=200)

    with pytest.raises(core.AuthError):
        core.login(FakeSession(), "user", "pass")


def test_list_activities_requests_full_page_and_caps():
    """pageSize is sent so we get more than the server's default 10, and the
    result is still capped at max_activities as a safety belt."""
    captured = {}

    class FakeSession:
        def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            items = [{"RideId": i, "Title": f"Ride {i}", "StartTime": "2026-05-28 19:20:42"}
                     for i in range(50)]
            return FakeResponse(json_data={"item": items, "total": 59})

    acts = core.list_activities(FakeSession(), 50)
    assert captured["params"] == {"pageNo": 1, "pageSize": 50}
    assert len(acts) == 50
    assert acts[0].ride_id == 0


def test_list_activities_caps_when_server_returns_extra():
    class FakeSession:
        def get(self, url, params=None):
            items = [{"RideId": i, "Title": "", "StartTime": ""} for i in range(20)]
            return FakeResponse(json_data={"item": items, "total": 20})

    acts = core.list_activities(FakeSession(), 5)
    assert len(acts) == 5


# --------------------------------------------------------------------------- #
# sync() orchestration
# --------------------------------------------------------------------------- #

@pytest.fixture
def stub_sync(monkeypatch, tmp_path):
    """Replace every network leaf so sync() runs offline. Returns a recorder."""
    rec = {
        "downloaded": [],
        "uploaded": [],
        "dropbox": [],
        "typed": [],
        "existing": set(),
        "dropbox_existing": set(),
        "dropbox_ok": True,
    }

    monkeypatch.setattr(core, "login", lambda s, u, p: {"Authorization": "x"})
    monkeypatch.setattr(
        core,
        "list_activities",
        lambda s, m: [
            core.Activity(1, "Ride 1", "2026-05-28 19:20:42"),
            core.Activity(2, "Ride 2", "2026-05-26 18:47:06"),
            core.Activity(3, "Ride 3", "2026-05-24 08:27:17"),
        ],
    )
    monkeypatch.setattr(core, "resolve_fit_url", lambda s, h, r: f"http://x/{r}.fit")

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"FIT")
        rec["downloaded"].append(dest.name)
        return dest

    monkeypatch.setattr(core, "download_fit", fake_download)
    monkeypatch.setattr(
        core, "fetch_uploaded_external_ids", lambda k, o, n: rec["existing"]
    )

    def fake_upload(fp, title, ride_id, key):
        rec["uploaded"].append(ride_id)
        return f"i{ride_id}"

    monkeypatch.setattr(core, "upload_to_intervals", fake_upload)

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
    monkeypatch.setattr(
        core,
        "set_activity_type",
        lambda aid, t, k: (rec["typed"].append((aid, t)) or True),
    )

    rec["tmp"] = tmp_path
    return rec


def _config(tmp_path, **overrides):
    base = dict(
        igp_user="u",
        igp_password="p",
        intervals_api_key="k",
        dropbox_refresh_token="dbx-refresh",
        dropbox_app_key="dbx-app",
        download_dir=tmp_path,
        delete_after_upload=False,
        force_resync=False,
        activity_type="",
        list_activities=False,
        get_download_url=False,
        download_fit=True,
        upload_intervals=True,
        upload_dropbox=False,
        dropbox_folder="/intervalssync-fit",
        dropbox_date_filenames=True,
    )
    base.update(overrides)
    return core.SyncConfig(**base)


def test_sync_skips_already_uploaded(stub_sync):
    stub_sync["existing"] = {"igpsport_1", "igpsport_2"}
    result = core.sync(_config(stub_sync["tmp"]))
    assert result.skipped == 2
    assert result.uploaded == 1
    assert stub_sync["downloaded"] == ["igpsport_3.fit"]


def test_sync_force_resync_processes_all(stub_sync):
    stub_sync["existing"] = {"igpsport_1", "igpsport_2", "igpsport_3"}
    result = core.sync(_config(stub_sync["tmp"], force_resync=True))
    assert result.skipped == 0
    assert result.uploaded == 3


def test_sync_download_only_does_not_skip(stub_sync):
    stub_sync["existing"] = {"igpsport_1", "igpsport_2", "igpsport_3"}
    result = core.sync(_config(stub_sync["tmp"], upload_intervals=False))
    assert result.downloaded == 3
    assert result.skipped == 0
    assert result.uploaded == 0


def test_sync_sets_activity_type_when_configured(stub_sync):
    core.sync(_config(stub_sync["tmp"], activity_type="MountainBikeRide"))
    assert stub_sync["typed"] == [
        ("i1", "MountainBikeRide"),
        ("i2", "MountainBikeRide"),
        ("i3", "MountainBikeRide"),
    ]


def test_sync_skips_type_when_empty(stub_sync):
    core.sync(_config(stub_sync["tmp"], activity_type=""))
    assert stub_sync["typed"] == []


def test_sync_deletes_file_after_upload_when_enabled(stub_sync):
    core.sync(_config(stub_sync["tmp"], delete_after_upload=True))
    assert not (stub_sync["tmp"] / "igpsport_1.fit").exists()


def test_sync_keeps_file_when_delete_disabled(stub_sync):
    core.sync(_config(stub_sync["tmp"], delete_after_upload=False))
    assert (stub_sync["tmp"] / "igpsport_1.fit").exists()


def test_sync_does_not_upload_to_dropbox_when_disabled(stub_sync):
    core.sync(_config(stub_sync["tmp"], upload_dropbox=False))
    assert stub_sync["dropbox"] == []


def test_sync_uploads_to_dropbox_after_intervals(stub_sync):
    result = core.sync(_config(stub_sync["tmp"], upload_dropbox=True))
    assert result.uploaded == 3
    assert result.uploaded_dropbox == 3
    assert [item[0] for item in stub_sync["dropbox"]] == [
        "ride-0-2026-05-28-19-20-42.fit",
        "ride-0-2026-05-26-18-47-06.fit",
        "ride-0-2026-05-24-08-27-17.fit",
    ]
    assert stub_sync["dropbox"][0][1:4] == ("dbx-refresh", "dbx-app", "/intervalssync-fit")
    assert stub_sync["dropbox"][0][4] == "igpsport_1.fit"


def test_sync_uploads_to_dropbox_even_when_intervals_skips(stub_sync):
    # Already on intervals.icu, but not yet in Dropbox: the targets are
    # independent, so all three still get pushed to Dropbox.
    stub_sync["existing"] = {"igpsport_1", "igpsport_2"}
    result = core.sync(_config(stub_sync["tmp"], upload_dropbox=True))
    assert result.skipped == 2
    assert result.uploaded == 1
    assert result.uploaded_dropbox == 3
    assert [item[0] for item in stub_sync["dropbox"]] == [
        "ride-0-2026-05-28-19-20-42.fit",
        "ride-0-2026-05-26-18-47-06.fit",
        "ride-0-2026-05-24-08-27-17.fit",
    ]


def test_sync_uploads_to_dropbox_when_intervals_disabled(stub_sync):
    result = core.sync(
        _config(stub_sync["tmp"], upload_intervals=False, upload_dropbox=True)
    )
    assert result.uploaded == 0
    assert stub_sync["uploaded"] == []
    assert result.uploaded_dropbox == 3
    assert [item[0] for item in stub_sync["dropbox"]] == [
        "ride-0-2026-05-28-19-20-42.fit",
        "ride-0-2026-05-26-18-47-06.fit",
        "ride-0-2026-05-24-08-27-17.fit",
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
        "igpsport_1.fit",
        "igpsport_2.fit",
        "igpsport_3.fit",
    ]


def test_sync_skips_dropbox_for_rides_already_in_dropbox(stub_sync):
    stub_sync["dropbox_existing"] = {
        "ride-0-2026-05-28-19-20-42.fit",
        "ride-0-2026-05-26-18-47-06.fit",
    }
    result = core.sync(
        _config(stub_sync["tmp"], upload_intervals=False, upload_dropbox=True)
    )
    assert result.skipped_dropbox == 2
    assert result.uploaded_dropbox == 1
    assert [item[0] for item in stub_sync["dropbox"]] == [
        "ride-0-2026-05-24-08-27-17.fit"
    ]


def test_sync_skips_dropbox_default_filenames_when_configured(stub_sync):
    stub_sync["dropbox_existing"] = {"igpsport_1.fit", "igpsport_2.fit"}
    result = core.sync(
        _config(
            stub_sync["tmp"],
            upload_intervals=False,
            upload_dropbox=True,
            dropbox_date_filenames=False,
        )
    )
    assert result.skipped_dropbox == 2
    assert result.uploaded_dropbox == 1
    assert [item[0] for item in stub_sync["dropbox"]] == ["igpsport_3.fit"]


def test_sync_force_resync_uploads_all_to_dropbox(stub_sync):
    stub_sync["existing"] = {"igpsport_1", "igpsport_2", "igpsport_3"}
    stub_sync["dropbox_existing"] = {
        "ride-0-2026-05-28-19-20-42.fit",
        "ride-0-2026-05-26-18-47-06.fit",
        "ride-0-2026-05-24-08-27-17.fit",
    }
    result = core.sync(
        _config(stub_sync["tmp"], force_resync=True, upload_dropbox=True)
    )
    assert result.skipped == 0
    assert result.skipped_dropbox == 0
    assert result.uploaded_dropbox == 3


def test_sync_keeps_file_when_dropbox_upload_fails(stub_sync):
    stub_sync["dropbox_ok"] = False
    result = core.sync(
        _config(stub_sync["tmp"], delete_after_upload=True, upload_dropbox=True)
    )
    assert result.uploaded == 3
    assert result.failed_dropbox == 3
    assert (stub_sync["tmp"] / "igpsport_1.fit").exists()


def test_sync_deletes_file_after_intervals_and_dropbox_when_enabled(stub_sync):
    result = core.sync(
        _config(stub_sync["tmp"], delete_after_upload=True, upload_dropbox=True)
    )
    assert result.uploaded_dropbox == 3
    assert not (stub_sync["tmp"] / "igpsport_1.fit").exists()


def test_sync_requires_dropbox_app_key_when_enabled(stub_sync):
    with pytest.raises(core.SyncError, match="Dropbox app key"):
        core.sync(
            _config(
                stub_sync["tmp"],
                upload_dropbox=True,
                dropbox_app_key=None,
            )
        )


def test_sync_requires_dropbox_connection_when_enabled(stub_sync):
    with pytest.raises(core.SyncError, match="Connect Dropbox"):
        core.sync(
            _config(
                stub_sync["tmp"],
                upload_dropbox=True,
                dropbox_refresh_token=None,
            )
        )
