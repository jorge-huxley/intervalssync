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


def test_activity_date_range_parses_dotted_dates():
    """Some iGPSPORT accounts return date-only 'YYYY.MM.DD' start times."""
    acts = [
        core.Activity(1, "a", "2026.07.19"),
        core.Activity(2, "b", "2026.05.03"),
    ]
    oldest, newest = core._activity_date_range(acts)
    assert oldest == date(2026, 5, 2)
    assert newest == date(2026, 7, 20)


def test_parse_igp_start_time_formats():
    assert core.parse_igp_start_time("2026-05-28 19:20:42").date() == date(2026, 5, 28)
    assert core.parse_igp_start_time("2026.07.19").date() == date(2026, 7, 19)
    assert core.parse_igp_start_time("unknown date") is None


def test_dropbox_filename_for_dotted_date():
    act = core.Activity(1, "Ride", "2026.07.19")
    assert core.dropbox_filename_for(act) == "ride-0-2026-07-19-00-00-00.fit"


def test_activity_date_range_fallback_when_unparseable():
    acts = [core.Activity(1, "a", "unknown date")]
    oldest, newest = core._activity_date_range(acts)
    assert (newest - oldest).days >= 365


def test_upload_201_returns_created_activity_from_activities(monkeypatch, tmp_path):
    fit = tmp_path / "igpsport_1.fit"
    fit.write_bytes(b"FIT")
    monkeypatch.setattr(
        intervals_icu.requests,
        "post",
        lambda *a, **k: FakeResponse(
            status=201,
            json_data={"id": "iX", "activities": [{"id": "  i999  "}]},
        ),
    )
    result = core.upload_to_intervals(fit, "Ride", 1, "key")
    assert result.activity_id == "i999"
    assert result.created is True


def test_upload_200_returns_linked_activity_from_top_level_id(monkeypatch, tmp_path):
    fit = tmp_path / "igpsport_1.fit"
    fit.write_bytes(b"FIT")
    monkeypatch.setattr(
        intervals_icu.requests,
        "post",
        lambda *a, **k: FakeResponse(
            status=200,
            json_data={"id": "  iTOP  ", "activities": []},
        ),
    )
    result = core.upload_to_intervals(fit, "Ride", 1, "key")
    assert result.activity_id == "iTOP"
    assert result.created is False


@pytest.mark.parametrize(
    "status,json_data",
    [
        (500, None),
        (200, {"activities": []}),
        (200, {"activities": [{"id": ""}]}),
        (200, {"activities": {"unexpected": "value"}}),
        (201, {"activities": "unexpected"}),
        (200, {"activities": 42}),
        (201, {}),
    ],
)
def test_upload_returns_none_on_failure_or_missing_id(
    monkeypatch, tmp_path, status, json_data
):
    fit = tmp_path / "igpsport_1.fit"
    fit.write_bytes(b"FIT")
    monkeypatch.setattr(
        intervals_icu.requests,
        "post",
        lambda *a, **k: FakeResponse(status=status, json_data=json_data),
    )
    assert core.upload_to_intervals(fit, "Ride", 1, "key") is None


def test_upload_malformed_activities_uses_valid_top_level_id(monkeypatch, tmp_path):
    fit = tmp_path / "igpsport_1.fit"
    fit.write_bytes(b"FIT")
    monkeypatch.setattr(
        intervals_icu.requests,
        "post",
        lambda *a, **k: FakeResponse(
            status=200,
            json_data={
                "activities": {"unexpected": "value"},
                "id": "  iTOP  ",
            },
        ),
    )

    result = core.upload_to_intervals(fit, "Ride", 1, "key")

    assert result == intervals_icu.ActivityUploadResult("iTOP", created=False)


@pytest.mark.parametrize("bad_id", [{"bad": "shape"}, ["i1"], True, 42, "", "   "])
def test_upload_rejects_malformed_activity_ids(monkeypatch, tmp_path, bad_id):
    fit = tmp_path / "igpsport_1.fit"
    fit.write_bytes(b"FIT")
    monkeypatch.setattr(
        intervals_icu.requests,
        "post",
        lambda *a, **k: FakeResponse(
            status=200,
            json_data={"activities": [{"id": bad_id}], "id": bad_id},
        ),
    )

    assert core.upload_to_intervals(fit, "Ride", 1, "key") is None


def test_upload_invalid_nested_id_falls_back_to_trimmed_top_level_id(
    monkeypatch, tmp_path
):
    fit = tmp_path / "igpsport_1.fit"
    fit.write_bytes(b"FIT")
    monkeypatch.setattr(
        intervals_icu.requests,
        "post",
        lambda *a, **k: FakeResponse(
            status=201,
            json_data={
                "activities": [{"id": {"bad": "shape"}}],
                "id": "  iTOP  ",
            },
        ),
    )

    result = core.upload_to_intervals(fit, "Ride", 1, "key")

    assert result == intervals_icu.ActivityUploadResult("iTOP", created=True)


def test_fetch_activity_identities_returns_ids_and_external_id_map(monkeypatch):
    monkeypatch.setattr(
        intervals_icu.requests,
        "get",
        lambda *a, **k: FakeResponse(
            json_data=[
                {"id": "  i1  ", "external_id": "  igpsport_1  "},
                {"id": "i2", "external_id": None},
                {},
                {"id": "i3", "external_id": "igpsport_3"},
            ]
        ),
    )
    identities = core.fetch_activity_identities(
        "key", date(2026, 1, 1), date(2026, 1, 2)
    )
    assert identities.activity_ids == {"i1", "i2", "i3"}
    assert identities.external_ids == {
        "igpsport_1": "i1",
        "igpsport_3": "i3",
    }


@pytest.mark.parametrize("bad_id", [{"bad": "shape"}, ["i1"], True, 42, "", "   "])
def test_fetch_activity_identities_rejects_malformed_activity_id(monkeypatch, bad_id):
    monkeypatch.setattr(
        intervals_icu.requests,
        "get",
        lambda *a, **k: FakeResponse(json_data=[{"id": bad_id}]),
    )

    with pytest.raises(ValueError, match="activity id"):
        core.fetch_activity_identities("key", date(2026, 1, 1), date(2026, 1, 2))


@pytest.mark.parametrize(
    "bad_external_id",
    [{"bad": "shape"}, ["igpsport_1"], True, 42, "", "   "],
)
def test_fetch_activity_identities_rejects_malformed_external_id(
    monkeypatch, bad_external_id
):
    monkeypatch.setattr(
        intervals_icu.requests,
        "get",
        lambda *a, **k: FakeResponse(
            json_data=[{"id": "i1", "external_id": bad_external_id}]
        ),
    )

    with pytest.raises(ValueError, match="external_id"):
        core.fetch_activity_identities("key", date(2026, 1, 1), date(2026, 1, 2))


def test_identity_gets_use_30_second_timeout(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url == intervals_icu.INTERVALS_ACTIVITIES_URL:
            return FakeResponse(json_data=[])
        return FakeResponse(status=200)

    monkeypatch.setattr(intervals_icu.requests, "get", fake_get)

    core.fetch_activity_identities("key", date(2026, 1, 1), date(2026, 1, 2))
    assert core.activity_exists("key", "i1") is True
    assert [kwargs["timeout"] for _, kwargs in calls] == [30, 30]


@pytest.mark.parametrize("status,expected", [(200, True), (404, False)])
def test_activity_exists_distinguishes_present_and_deleted(monkeypatch, status, expected):
    monkeypatch.setattr(
        intervals_icu.requests,
        "get",
        lambda *a, **k: FakeResponse(status=status),
    )
    assert core.activity_exists("key", "i1") is expected


@pytest.mark.parametrize("status", [201, 204, 301, 401, 403, 429, 500, 503])
def test_activity_exists_raises_for_unverified_status(monkeypatch, status):
    monkeypatch.setattr(
        intervals_icu.requests,
        "get",
        lambda *a, **k: FakeResponse(status=status),
    )
    with pytest.raises(core.requests.HTTPError):
        core.activity_exists("key", "i1")


@pytest.mark.parametrize("status,expected", [(200, True), (400, False)])
def test_set_activity_type(monkeypatch, status, expected):
    monkeypatch.setattr(intervals_icu.requests, "put", lambda *a, **k: FakeResponse(status=status))
    assert core.set_activity_type("i1", "MountainBikeRide", "key") is expected


def test_login_builds_bearer_from_access_token():
    class FakeSession:
        headers: dict[str, str] = {}

        def post(self, *a, **k):
            return FakeResponse(
                status=200,
                json_data={"data": {"access_token": "intl.jwt.token"}},
            )

        def update(self, headers):
            self.headers.update(headers)

    session = FakeSession()
    headers = core.login(session, "user+tag@example.com", "igp&1%!")
    assert headers == {"Authorization": "Bearer intl.jwt.token"}


def test_login_raises_when_access_token_missing():
    class FakeSession:
        def post(self, *a, **k):
            return FakeResponse(status=200, json_data={"message": "Password error"})

    with pytest.raises(core.AuthError, match="Password error"):
        core.login(FakeSession(), "user", "pass", region="china")


def test_login_international_adds_retry_hint_on_failure():
    class FakeSession:
        def post(self, *a, **k):
            return FakeResponse(status=200, json_data={"message": "Password error"})

    with pytest.raises(core.AuthError, match="app.igpsport.cn"):
        core.login(FakeSession(), "user", "pass")


def test_login_china_parses_access_token():
    class FakeSession:
        headers: dict[str, str] = {}

        def post(self, url, json=None):
            assert json == {
                "appId": "igpsport-web",
                "username": "13800000000",
                "password": "secret",
            }
            return FakeResponse(
                status=200,
                json_data={"data": {"access_token": "cn.jwt.token"}},
            )

        def update(self, headers):
            self.headers.update(headers)

    session = FakeSession()
    headers = core.login(session, "13800000000", "secret", region="china")
    assert headers == {"Authorization": "Bearer cn.jwt.token"}
    assert session.headers["Authorization"] == "Bearer cn.jwt.token"


def test_login_china_raises_when_token_missing():
    class FakeSession:
        def post(self, *a, **k):
            return FakeResponse(status=403, json_data={"code": 1002, "message": "Password error"})

    with pytest.raises(core.AuthError, match="Password error"):
        core.login(FakeSession(), "13800000000", "bad", region="china")


def test_list_activities_china_parses_camel_case_rows():
    captured = {}

    class FakeSession:
        def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return FakeResponse(
                json_data={
                    "data": {
                        "rows": [
                            {
                                "rideId": 42,
                                "title": "Morning ride",
                                "startTime": "2026-06-01 08:00:00",
                            }
                        ]
                    }
                }
            )

    acts = core.list_activities(FakeSession(), 10, region="china")
    assert "queryMyActivity" in captured["url"]
    assert captured["params"] == {
        "pageNo": "1",
        "pageSize": "10",
        "sort": "1",
        "reqType": "0",
    }
    assert len(acts) == 1
    assert acts[0].ride_id == 42
    assert acts[0].title == "Morning ride"
    assert acts[0].start_time == "2026-06-01 08:00:00"


def test_list_activities_requests_full_page_and_caps():
    """Paginates when the API caps each page at 20 rows."""
    captured_pages: list[dict] = []

    class FakeSession:
        def get(self, url, params=None):
            captured_pages.append(dict(params or {}))
            page_no = int(params["pageNo"])
            page_size = int(params["pageSize"])
            start = (page_no - 1) * page_size
            end = min(start + page_size, 50)
            rows = [
                {
                    "rideId": i,
                    "title": f"Ride {i}",
                    "startTime": "2026-05-28 19:20:42",
                }
                for i in range(start, end)
            ]
            return FakeResponse(json_data={"data": {"rows": rows}})

    acts = core.list_activities(FakeSession(), 50)
    assert len(captured_pages) == 3
    assert captured_pages[0]["pageNo"] == "1"
    assert captured_pages[0]["pageSize"] == "20"
    assert captured_pages[1]["pageNo"] == "2"
    assert captured_pages[2]["pageNo"] == "3"
    assert len(acts) == 50
    assert acts[0].ride_id == 0
    assert acts[-1].ride_id == 49


def test_list_activities_paginates_when_api_caps_page_size():
    """Real API returns at most 20 rows per page even when pageSize is larger."""
    captured_pages: list[dict] = []

    class FakeSession:
        def get(self, url, params=None):
            captured_pages.append(dict(params or {}))
            page_no = int(params["pageNo"])
            # Simulate iGPSPORT: always cap at 20 rows per page.
            start = (page_no - 1) * 20
            if start >= 35:
                rows = []
            else:
                end = min(start + 20, 35)
                rows = [
                    {"rideId": i, "title": f"Ride {i}", "startTime": "2026-05-28 19:20:42"}
                    for i in range(start, end)
                ]
            return FakeResponse(json_data={"data": {"rows": rows}})

    acts = core.list_activities(FakeSession(), 30)
    assert len(captured_pages) == 2
    assert captured_pages[0] == {
        "pageNo": "1",
        "pageSize": "20",
        "sort": "1",
        "reqType": "0",
    }
    assert captured_pages[1]["pageNo"] == "2"
    assert len(acts) == 30
    assert acts[0].ride_id == 0
    assert acts[-1].ride_id == 29


def test_list_activities_caps_when_server_returns_extra():
    class FakeSession:
        def get(self, url, params=None):
            rows = [{"rideId": i, "title": "", "startTime": ""} for i in range(20)]
            return FakeResponse(json_data={"data": {"rows": rows}})

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
        "activity_ids": set(),
        "fetch_error": None,
        "verified": {},
        "upload_results": {},
        "dropbox_existing": set(),
        "dropbox_ok": True,
    }

    monkeypatch.setattr(core, "login", lambda s, u, p, *a, **k: {"Authorization": "x"})
    monkeypatch.setattr(
        core,
        "list_activities",
        lambda s, m, *a, **k: [
            core.Activity(1, "Ride 1", "2026-05-28 19:20:42"),
            core.Activity(2, "Ride 2", "2026-05-26 18:47:06"),
            core.Activity(3, "Ride 3", "2026-05-24 08:27:17"),
        ],
    )
    monkeypatch.setattr(core, "resolve_fit_url", lambda s, h, r, *a, **k: f"http://x/{r}.fit")

    def fake_download(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"FIT")
        rec["downloaded"].append(dest.name)
        return dest

    monkeypatch.setattr(core, "download_fit", fake_download)
    def fake_fetch_identities(key, oldest, newest):
        if rec["fetch_error"]:
            raise rec["fetch_error"]
        external_ids = {
            ext: f"existing-{ext}"
            for ext in rec["existing"]
        }
        return intervals_icu.ActivityIdentities(
            set(rec["activity_ids"]) | set(external_ids.values()),
            external_ids,
        )

    monkeypatch.setattr(core, "fetch_activity_identities", fake_fetch_identities)

    def fake_activity_exists(key, activity_id):
        outcome = rec["verified"].get(activity_id, True)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(core, "activity_exists", fake_activity_exists)

    def fake_upload(fp, title, ride_id, key):
        rec["uploaded"].append(ride_id)
        return rec["upload_results"].get(
            ride_id,
            intervals_icu.ActivityUploadResult(f"i{ride_id}", created=True),
        )

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
        uploaded_activities={},
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


def test_sync_rejects_malformed_activity_discovery_before_fit_work(monkeypatch, tmp_path):
    resolved = []
    downloaded = []
    monkeypatch.setattr(core, "login", lambda *a, **k: {"Authorization": "x"})
    monkeypatch.setattr(
        core,
        "list_activities",
        lambda *a, **k: [core.Activity(1, "Ride", "2026-05-28 19:20:42")],
    )
    monkeypatch.setattr(
        intervals_icu.requests,
        "get",
        lambda *a, **k: FakeResponse(json_data={"error": "synthetic lookup failure"}),
    )

    def fake_resolve(*args, **kwargs):
        resolved.append(args[2])
        return None

    def fake_download(url, dest):
        downloaded.append(dest.name)
        return dest

    monkeypatch.setattr(core, "resolve_fit_url", fake_resolve)
    monkeypatch.setattr(core, "download_fit", fake_download)

    with pytest.raises(core.SyncError, match="Could not check intervals.icu"):
        core.sync(_config(tmp_path))

    assert resolved == []
    assert downloaded == []


def test_sync_rejects_malformed_discovered_id_before_fit_work(monkeypatch, tmp_path):
    resolved = []
    downloaded = []
    monkeypatch.setattr(core, "login", lambda *a, **k: {"Authorization": "x"})
    monkeypatch.setattr(
        core,
        "list_activities",
        lambda *a, **k: [core.Activity(1, "Ride", "2026-05-28 19:20:42")],
    )
    monkeypatch.setattr(
        intervals_icu.requests,
        "get",
        lambda *a, **k: FakeResponse(
            json_data=[
                {"id": {"bad": "shape"}, "external_id": "igpsport_1"}
            ]
        ),
    )
    monkeypatch.setattr(
        core,
        "resolve_fit_url",
        lambda *a, **k: resolved.append(a[2]),
    )
    monkeypatch.setattr(
        core,
        "download_fit",
        lambda url, dest: downloaded.append(dest.name),
    )

    with pytest.raises(core.SyncError, match="Could not check intervals.icu"):
        core.sync(_config(tmp_path))

    assert resolved == []
    assert downloaded == []


def test_sync_identity_timeout_stops_before_fit_work(monkeypatch, tmp_path):
    resolved = []
    downloaded = []
    monkeypatch.setattr(core, "login", lambda *a, **k: {"Authorization": "x"})
    monkeypatch.setattr(
        core,
        "list_activities",
        lambda *a, **k: [core.Activity(1, "Ride", "2026-05-28 19:20:42")],
    )

    def fake_get(*args, **kwargs):
        assert kwargs["timeout"] == 30
        raise core.requests.Timeout("identity lookup timed out")

    monkeypatch.setattr(intervals_icu.requests, "get", fake_get)
    monkeypatch.setattr(
        core,
        "resolve_fit_url",
        lambda *a, **k: resolved.append(a[2]),
    )
    monkeypatch.setattr(
        core,
        "download_fit",
        lambda url, dest: downloaded.append(dest.name),
    )

    with pytest.raises(core.SyncError, match="identity lookup timed out"):
        core.sync(_config(tmp_path))

    assert resolved == []
    assert downloaded == []


def test_sync_malformed_upload_counts_failure_and_keeps_prior_mapping(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "login", lambda *a, **k: {"Authorization": "x"})
    monkeypatch.setattr(
        core,
        "list_activities",
        lambda *a, **k: [
            core.Activity(1, "Existing", "2026-05-28 19:20:42"),
            core.Activity(2, "Malformed", "2026-05-27 19:20:42"),
        ],
    )
    monkeypatch.setattr(
        core,
        "fetch_activity_identities",
        lambda *a, **k: intervals_icu.ActivityIdentities(
            {"existing-i1"},
            {"igpsport_1": "existing-i1"},
        ),
    )
    monkeypatch.setattr(core, "resolve_fit_url", lambda *a, **k: "https://fit.test/2")

    def fake_download(url, dest):
        dest.write_bytes(b"FIT")
        return dest

    monkeypatch.setattr(core, "download_fit", fake_download)
    monkeypatch.setattr(
        intervals_icu.requests,
        "post",
        lambda *a, **k: FakeResponse(
            status=200,
            json_data={"activities": {"unexpected": "value"}},
        ),
    )

    result = core.sync(_config(tmp_path, delete_after_upload=True))

    assert result.failed == 1
    assert result.uploaded == 0
    assert result.linked == 0
    assert result.activity_map == {"1": "existing-i1"}
    assert (tmp_path / "igpsport_2.fit").exists()


def test_sync_skips_already_uploaded(stub_sync):
    stub_sync["existing"] = {"igpsport_1", "igpsport_2"}
    result = core.sync(_config(stub_sync["tmp"]))
    assert result.skipped == 2
    assert result.uploaded == 1
    assert stub_sync["downloaded"] == ["igpsport_3.fit"]


def test_apply_uploaded_activity_map_updates_and_prunes():
    uploaded = {"1": "old-i1", "2": "i2"}
    result = core.SyncResult(
        activity_map={"1": "new-i1", "3": "i3"},
        pruned_keys=["1", "2"],
    )

    core.apply_uploaded_activity_map(uploaded, result)

    assert uploaded == {"1": "new-i1", "3": "i3"}


def test_checkpoint_saves_discovery_and_pruning_before_download(stub_sync, monkeypatch):
    stub_sync["existing"] = {"igpsport_1"}
    stub_sync["verified"]["deleted-i2"] = False
    persisted = {"2": "deleted-i2", "99": "unrelated"}

    def fail_download(*args):
        assert persisted == {"1": "existing-igpsport_1", "99": "unrelated"}
        raise core.requests.Timeout("download failed")

    monkeypatch.setattr(core, "download_fit", fail_download)
    with pytest.raises(core.requests.Timeout, match="download failed"):
        core.sync(
            _config(stub_sync["tmp"], uploaded_activities=dict(persisted)),
            on_activity_map=lambda result: core.apply_uploaded_activity_map(persisted, result),
        )


def test_checkpoint_write_error_stops_before_more_remote_work(stub_sync):
    def fail_save(result):
        assert result.activity_map == {"1": "i1"}
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        core.sync(
            _config(stub_sync["tmp"], activity_type="GravelRide"),
            on_activity_map=fail_save,
        )

    assert stub_sync["uploaded"] == [1]
    assert stub_sync["downloaded"] == ["igpsport_1.fit"]
    assert stub_sync["typed"] == []


def test_sync_expected_external_id_seeds_mapping_without_download(stub_sync):
    stub_sync["existing"] = {"igpsport_1"}

    result = core.sync(_config(stub_sync["tmp"]))

    assert result.activity_map == {
        "1": "existing-igpsport_1",
        "2": "i2",
        "3": "i3",
    }
    assert result.skipped == 1
    assert "igpsport_1.fit" not in stub_sync["downloaded"]


def test_sync_mapped_id_in_window_skips_without_verification_or_download(stub_sync):
    stub_sync["activity_ids"] = {"mapped-i1"}
    stub_sync["verified"]["mapped-i1"] = AssertionError("must not verify")

    result = core.sync(
        _config(stub_sync["tmp"], uploaded_activities={"1": "mapped-i1"})
    )

    assert result.skipped == 1
    assert "igpsport_1.fit" not in stub_sync["downloaded"]


def test_sync_mapped_id_get_200_skips_without_download(stub_sync):
    stub_sync["verified"]["mapped-i1"] = True

    result = core.sync(
        _config(stub_sync["tmp"], uploaded_activities={"1": "mapped-i1"})
    )

    assert result.skipped == 1
    assert result.pruned_keys == []
    assert "igpsport_1.fit" not in stub_sync["downloaded"]


def test_sync_mapped_id_get_404_prunes_then_uploads(stub_sync):
    stub_sync["verified"]["gone-i1"] = False

    result = core.sync(
        _config(stub_sync["tmp"], uploaded_activities={"1": "gone-i1"})
    )

    assert result.pruned_keys == ["1"]
    assert result.uploaded == 3
    assert result.activity_map["1"] == "i1"
    assert "igpsport_1.fit" in stub_sync["downloaded"]


def test_sync_initial_identity_lookup_error_fails_before_download(stub_sync):
    stub_sync["fetch_error"] = core.requests.ConnectionError("lookup failed")

    with pytest.raises(core.SyncError, match="Could not check intervals.icu"):
        core.sync(_config(stub_sync["tmp"]))

    assert stub_sync["downloaded"] == []


@pytest.mark.parametrize(
    "error",
    [
        core.requests.ConnectionError("connection failed"),
        core.requests.HTTPError("HTTP 401"),
        core.requests.HTTPError("HTTP 403"),
        core.requests.HTTPError("HTTP 429"),
        core.requests.HTTPError("HTTP 500"),
        core.requests.HTTPError("HTTP 503"),
    ],
)
def test_sync_mapping_verification_error_preflights_before_any_download(
    stub_sync, error
):
    stub_sync["verified"]["mapped-i2"] = error

    with pytest.raises(core.SyncError, match="Could not verify intervals.icu activity"):
        core.sync(
            _config(stub_sync["tmp"], uploaded_activities={"2": "mapped-i2"})
        )

    assert stub_sync["downloaded"] == []


def test_sync_201_records_mapping_and_sets_activity_type(stub_sync):
    result = core.sync(
        _config(stub_sync["tmp"], activity_type="MountainBikeRide")
    )

    assert result.uploaded == 3
    assert result.linked == 0
    assert result.activity_map == {"1": "i1", "2": "i2", "3": "i3"}
    assert stub_sync["typed"] == [
        ("i1", "MountainBikeRide"),
        ("i2", "MountainBikeRide"),
        ("i3", "MountainBikeRide"),
    ]


def test_sync_200_links_foreign_duplicate_without_setting_type(stub_sync):
    stub_sync["upload_results"][1] = intervals_icu.ActivityUploadResult(
        "foreign-i1", created=False
    )

    result = core.sync(
        _config(stub_sync["tmp"], activity_type="MountainBikeRide")
    )

    assert result.uploaded == 2
    assert result.linked == 1
    assert result.activity_map["1"] == "foreign-i1"
    assert ("foreign-i1", "MountainBikeRide") not in stub_sync["typed"]


def test_sync_failed_upload_keeps_fit(stub_sync):
    stub_sync["upload_results"][1] = None

    result = core.sync(_config(stub_sync["tmp"], delete_after_upload=True))

    assert result.failed == 1
    assert (stub_sync["tmp"] / "igpsport_1.fit").exists()


def test_sync_repeat_cycle_uses_persisted_mapping_without_redownload(stub_sync):
    first = core.sync(_config(stub_sync["tmp"]))
    persisted = {}
    core.apply_uploaded_activity_map(persisted, first)
    stub_sync["downloaded"].clear()

    second = core.sync(
        _config(stub_sync["tmp"], uploaded_activities=dict(persisted))
    )

    assert second.skipped == 3
    assert stub_sync["downloaded"] == []


def test_sync_force_resync_processes_all(stub_sync):
    stub_sync["existing"] = {"igpsport_1", "igpsport_2", "igpsport_3"}
    result = core.sync(_config(stub_sync["tmp"], force_resync=True))
    assert result.skipped == 0
    assert result.uploaded == 3


def test_sync_force_resync_bypasses_identity_checks_and_classifies_results(stub_sync):
    stub_sync["fetch_error"] = AssertionError("must not discover")
    stub_sync["verified"]["mapped-i1"] = AssertionError("must not verify")
    stub_sync["upload_results"][1] = intervals_icu.ActivityUploadResult(
        "linked-i1", created=False
    )

    result = core.sync(
        _config(
            stub_sync["tmp"],
            force_resync=True,
            uploaded_activities={"1": "mapped-i1"},
        )
    )

    assert result.uploaded == 2
    assert result.linked == 1
    assert result.activity_map["1"] == "linked-i1"


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
