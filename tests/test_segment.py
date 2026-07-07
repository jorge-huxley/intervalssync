"""Tests for intervals.icu routes → iGPSPORT segment upload."""

from __future__ import annotations

import gzip
import json

import pytest

from intervalssync import intervals_icu
from intervalssync.igpsport import segment
from intervalssync.igpsport.core import SyncError
from intervalssync.intervals_icu import IntervalsRoute


def _sample_route(**overrides) -> IntervalsRoute:
    defaults = {
        "route_id": 42,
        "name": "Climb",
        "distance": 1200.0,
        "activity_count": 3,
        "latlngs": [[40.0, -3.0], [40.01, -3.01, 100.0], [40.02, -3.02, 150.0]],
        "most_recent_id": "i123",
        "description": "Test climb",
    }
    defaults.update(overrides)
    return IntervalsRoute(**defaults)


def test_parse_igpsport_ride_id():
    assert segment.parse_igpsport_ride_id("igpsport_85775035") == 85775035
    assert segment.parse_igpsport_ride_id("bryton_abc") is None
    assert segment.parse_igpsport_ride_id(None) is None


def test_intervals_route_to_segment_add():
    body = segment.intervals_route_to_segment_add(_sample_route(), ride_id=85775035)
    assert body["title"] == "Climb"
    assert body["description"] == "Test climb"
    assert body["rideId"] == 85775035
    assert body["distance"] == 1200.0
    assert body["segmentsStatus"] == 1
    assert body["startPosLat"] == 40.0
    assert body["endPosLat"] == 40.02
    info = body["segmentInfo"]
    assert info["start"] == 0
    assert info["end"] == 2
    assert len(info["coords"]) == 3
    assert info["coords"][1] == [40.01, -3.01, 100.0]
    assert len(info["time"]) == 3
    assert info["time"][0] == segment._FIT_EPOCH_UNIX


def test_intervals_route_to_segment_add_custom_title():
    body = segment.intervals_route_to_segment_add(
        _sample_route(), ride_id=1, title="Custom"
    )
    assert body["title"] == "Custom"


def test_intervals_route_to_segment_add_requires_two_points():
    route = _sample_route(latlngs=[[40.0, -3.0]])
    with pytest.raises(SyncError, match="fewer than 2"):
        segment.intervals_route_to_segment_add(route, ride_id=1)


def test_downsample_coords():
    coords = [[float(i), 0.0, 0.0] for i in range(5000)]
    sampled = segment._downsample_coords(coords, 2000)
    assert len(sampled) == 2000
    assert sampled[0] == coords[0]
    assert sampled[-1] == coords[-1]


def test_resolve_ride_id_from_override():
    ride_id = segment.resolve_ride_id(_sample_route(), intervals_api_key="key", igp_ride_id=99)
    assert ride_id == 99


def test_resolve_ride_id_from_external_id(monkeypatch):
    monkeypatch.setattr(
        intervals_icu,
        "fetch_activity_external_id",
        lambda api_key, activity_id, http=None: "igpsport_555",
    )
    ride_id = segment.resolve_ride_id(_sample_route(), intervals_api_key="key")
    assert ride_id == 555


def test_resolve_ride_id_raises_when_missing(monkeypatch):
    monkeypatch.setattr(
        intervals_icu,
        "fetch_activity_external_id",
        lambda api_key, activity_id, http=None: "strava_123",
    )
    with pytest.raises(SyncError, match="Could not resolve"):
        segment.resolve_ride_id(_sample_route(), intervals_api_key="key")


class FakeResponse:
    def __init__(self, *, status=200, json_data=None, content=b""):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._json = json_data
        self.content = content

    def json(self):
        return self._json


def test_segment_add_posts_gzip_json(monkeypatch):
    captured: dict = {}

    def fake_post(self, url, headers=None, data=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["data"] = data
        return FakeResponse(json_data={"code": 0, "data": {"isSucceed": True, "id": "seg-1"}})

    monkeypatch.setattr(segment.requests.Session, "post", fake_post)
    session = segment.requests.Session()
    segment_id = segment.segment_add(session, {"Authorization": "Bearer x"}, {"title": "A"})
    assert segment_id == "seg-1"
    assert captured["headers"]["Content-Encoding"] == "gzip"
    payload = json.loads(gzip.decompress(captured["data"]).decode("utf-8"))
    assert payload["title"] == "A"


def test_upload_segment_list_only(monkeypatch):
    routes = [_sample_route(route_id=1, name="One"), _sample_route(route_id=2, name="Two")]
    monkeypatch.setattr(segment, "list_routes", lambda key: routes)

    config = segment.SegmentUploadConfig(
        igp_user="u",
        igp_password="p",
        intervals_api_key="key",
        route_id=0,
        list_only=True,
    )
    result = segment.upload_segment(config)
    assert result.listed == 2
    assert result.uploaded == 0


def test_upload_segment_skips_when_already_uploaded(monkeypatch):
    route = _sample_route()
    monkeypatch.setattr(intervals_icu, "fetch_route", lambda key, route_id: route)
    monkeypatch.setattr(segment, "login", lambda s, u, p: {"Authorization": "Bearer t"})
    monkeypatch.setattr(segment, "fetch_member_id", lambda s, h: 1)
    monkeypatch.setattr(segment, "segment_create_check", lambda s, h: True)
    monkeypatch.setattr(segment, "fetch_segment_ids", lambda s, h, page_size=50: {"stored-id"})

    config = segment.SegmentUploadConfig(
        igp_user="u",
        igp_password="p",
        intervals_api_key="key",
        route_id=42,
        uploaded_segments={"42": "stored-id"},
    )
    result = segment.upload_segment(config)
    assert result.skipped == 1
    assert result.uploaded == 0
