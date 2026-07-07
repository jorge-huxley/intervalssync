"""Upload intervals.icu routes to iGPSPORT segments (mobile Segment API)."""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from .. import intervals_icu
from ..intervals_icu import IntervalsRoute
from .core import SyncError, login
from .interval_info import fetch_member_id, mobile_headers

IGPS_API = "https://prod.en.igpsport.com"
SEGMENT_CREATE_CHECK_URL = f"{IGPS_API}/service/mobile/api/Segment/SegmentCreateCheck"
SEGMENT_ADD_URL = f"{IGPS_API}/service/mobile/api/Segment/SegmentAdd"
SEGMENT_FIND_LIST_URL = f"{IGPS_API}/service/mobile/api/Segment/SegmentFindList"

IGPSPORT_EXTERNAL_PREFIX = "igpsport_"
# FIT epoch (1989-12-31 UTC) used for synthetic segmentInfo.time when no FIT is available.
_FIT_EPOCH_UNIX = 631065600
_MAX_COORDS = 2000

Progress = Callable[[str], None]


def _noop(_message: str) -> None:
    pass


@dataclass
class SegmentUploadResult:
    listed: int = 0
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0
    uploaded_map: dict[str, str] = field(default_factory=dict)
    pruned_keys: list[str] = field(default_factory=list)


@dataclass
class SegmentUploadConfig:
    igp_user: str
    igp_password: str
    intervals_api_key: str
    route_id: int
    igp_ride_id: int | None = None
    title: str | None = None
    uploaded_segments: dict[str, str] = field(default_factory=dict)
    force_resync: bool = False
    list_only: bool = False


def parse_igpsport_ride_id(external_id: str | None) -> int | None:
    """Parse igpsport_{rideId} from an intervals.icu external_id."""
    if not external_id or not external_id.startswith(IGPSPORT_EXTERNAL_PREFIX):
        return None
    suffix = external_id[len(IGPSPORT_EXTERNAL_PREFIX) :]
    try:
        return int(suffix)
    except ValueError:
        return None


def resolve_ride_id(
    route: IntervalsRoute,
    *,
    intervals_api_key: str,
    igp_ride_id: int | None = None,
    http: requests.Session | None = None,
) -> int:
    """Resolve iGPSPORT rideId from CLI override or linked activity external_id."""
    if igp_ride_id is not None:
        return igp_ride_id
    if route.most_recent_id:
        external_id = intervals_icu.fetch_activity_external_id(
            intervals_api_key,
            route.most_recent_id,
            http=http,
        )
        parsed = parse_igpsport_ride_id(external_id)
        if parsed is not None:
            return parsed
    raise SyncError(
        "Could not resolve iGPSPORT rideId for this route. "
        "Pass --igp-ride-id with an activity id from iGPSPORT, or use a route whose "
        "most recent activity was synced from iGPSPORT (external_id igpsport_{id})."
    )


def _normalize_coords(latlngs: list[list[float]]) -> list[list[float]]:
    """Convert intervals [[lat,lng],...] to iGPSPORT [[lat,lon,alt],...]."""
    coords: list[list[float]] = []
    for point in latlngs:
        if len(point) >= 3:
            coords.append([float(point[0]), float(point[1]), float(point[2])])
        elif len(point) >= 2:
            coords.append([float(point[0]), float(point[1]), 0.0])
    return coords


def _downsample_coords(coords: list[list[float]], max_points: int) -> list[list[float]]:
    if len(coords) <= max_points:
        return coords
    step = len(coords) / max_points
    sampled: list[list[float]] = []
    for i in range(max_points):
        idx = min(int(i * step), len(coords) - 1)
        sampled.append(coords[idx])
    if sampled[-1] is not coords[-1]:
        sampled[-1] = coords[-1]
    return sampled


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _path_distance_m(coords: list[list[float]]) -> float:
    total = 0.0
    for i in range(1, len(coords)):
        total += _haversine_m(
            coords[i - 1][0], coords[i - 1][1], coords[i][0], coords[i][1]
        )
    return total


def _elevation_stats(coords: list[list[float]]) -> tuple[float, float, float]:
    """Return total_ascent, total_descent, avg_slope (rise/run)."""
    ascent = 0.0
    descent = 0.0
    for i in range(1, len(coords)):
        delta = coords[i][2] - coords[i - 1][2]
        if delta > 0:
            ascent += delta
        elif delta < 0:
            descent += -delta
    horizontal = _path_distance_m(coords)
    avg_slope = (ascent - descent) / horizontal if horizontal > 0 else 0.0
    return ascent, descent, avg_slope


def _synthetic_fit_times(count: int) -> list[int]:
    return [_FIT_EPOCH_UNIX + i for i in range(count)]


def intervals_route_to_segment_add(
    route: IntervalsRoute,
    ride_id: int,
    *,
    title: str | None = None,
) -> dict[str, Any]:
    """Build SegmentAdd JSON body from an intervals.icu route."""
    coords = _normalize_coords(route.latlngs)
    if len(coords) < 2:
        raise SyncError(f"Route {route.route_id} has fewer than 2 coordinates.")
    coords = _downsample_coords(coords, _MAX_COORDS)

    ascent, descent, avg_slope = _elevation_stats(coords)
    distance = route.distance if route.distance is not None else _path_distance_m(coords)

    start = coords[0]
    end = coords[-1]
    return {
        "title": title or route.name,
        "description": route.description,
        "distance": float(distance),
        "avgSlope": avg_slope,
        "totalAscent": ascent,
        "totalDecline": descent,
        "exerciseType": 0,
        "roadSurfaceStatus": 0,
        "segmentsStatus": 1,
        "segmentsType": 0,
        "rideId": ride_id,
        "startPosLat": start[0],
        "startPosLon": start[1],
        "endPosLat": end[0],
        "endPosLon": end[1],
        "segmentInfo": {
            "start": 0,
            "end": len(coords) - 1,
            "coords": coords,
            "time": _synthetic_fit_times(len(coords)),
        },
    }


def segment_create_check(session: requests.Session, headers: dict[str, str]) -> bool:
    """POST SegmentCreateCheck (empty body). Returns True when allowed."""
    post_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
    resp = session.post(SEGMENT_CREATE_CHECK_URL, headers=post_headers, data=b"")
    if not resp.ok:
        return False
    try:
        body = resp.json()
    except ValueError:
        return False
    return body.get("code") == 0 and body.get("data") is True


def segment_add(
    session: requests.Session,
    headers: dict[str, str],
    body: dict[str, Any],
) -> str | None:
    """POST gzip-compressed SegmentAdd JSON; return new segment id on success."""
    payload = gzip.compress(json.dumps(body).encode("utf-8"))
    post_headers = {
        **headers,
        "Content-Type": "application/json; charset=UTF-8",
        "Content-Encoding": "gzip",
    }
    resp = session.post(SEGMENT_ADD_URL, headers=post_headers, data=payload)
    if not resp.ok:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    if data.get("code") != 0:
        return None
    payload_data = data.get("data") or {}
    if not isinstance(payload_data, dict):
        return None
    if not payload_data.get("isSucceed"):
        return None
    segment_id = payload_data.get("id")
    return str(segment_id) if segment_id else None


def fetch_segment_ids(
    session: requests.Session,
    headers: dict[str, str],
    *,
    page_size: int = 50,
) -> set[str]:
    """Return segment ids from SegmentFindList (FindType=1 = user's segments)."""
    ids: set[str] = set()
    page_index = 1
    while True:
        resp = session.get(
            SEGMENT_FIND_LIST_URL,
            params={"FindType": 1, "PageIndex": page_index, "PageSize": page_size},
            headers=headers,
        )
        if not resp.ok:
            break
        try:
            body = resp.json()
        except ValueError:
            break
        if body.get("code") != 0:
            break
        data = body.get("data") or {}
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
        total = data.get("total") if isinstance(data, dict) else None
        if total is not None and page_index * page_size >= int(total):
            break
        if len(items) < page_size:
            break
        page_index += 1
    return ids


def apply_uploaded_segment_map(
    uploaded_segments: dict[str, str],
    result: SegmentUploadResult,
) -> None:
    uploaded_segments.update(result.uploaded_map)
    for key in result.pruned_keys:
        uploaded_segments.pop(key, None)


def list_routes(intervals_api_key: str) -> list[IntervalsRoute]:
    try:
        return intervals_icu.fetch_routes(intervals_api_key)
    except requests.RequestException as exc:
        raise SyncError(f"Could not fetch intervals.icu routes: {exc}") from exc


def upload_segment(
    config: SegmentUploadConfig,
    progress: Progress | None = None,
) -> SegmentUploadResult:
    """Fetch one intervals.icu route and upload it as an iGPSPORT segment."""
    report = progress or _noop
    result = SegmentUploadResult()

    if config.list_only:
        routes = list_routes(config.intervals_api_key)
        result.listed = len(routes)
        for route in routes:
            report(
                f"  • {route.route_id} | {route.activity_count} rides | {route.name}"
            )
        return result

    report("Fetching route from intervals.icu…")
    try:
        route = intervals_icu.fetch_route(config.intervals_api_key, config.route_id)
    except requests.RequestException as exc:
        raise SyncError(f"Could not fetch intervals.icu route: {exc}") from exc
    except ValueError as exc:
        raise SyncError(str(exc)) from exc

    result.listed = 1
    route_key = str(route.route_id)

    report("Logging in to iGPSPORT…")
    session = requests.Session()
    try:
        auth_headers = login(session, config.igp_user, config.igp_password)
    except Exception as exc:
        raise SyncError(str(exc)) from exc

    member_id = fetch_member_id(session, auth_headers)
    headers = mobile_headers(auth_headers, member_id)

    report("Checking segment upload permission…")
    if not segment_create_check(session, headers):
        raise SyncError(
            "iGPSPORT SegmentCreateCheck failed — account may not be allowed to "
            "create segments, or authentication was rejected."
        )

    live_ids = fetch_segment_ids(session, headers)
    stored_id = config.uploaded_segments.get(route_key)
    on_igpsport = stored_id is not None and stored_id in live_ids

    if on_igpsport and not config.force_resync:
        report(f"↷ Skipping {route.name} — already on iGPSPORT ({stored_id}).")
        result.skipped = 1
    else:
        ride_id = resolve_ride_id(
            route,
            intervals_api_key=config.intervals_api_key,
            igp_ride_id=config.igp_ride_id,
            http=session,
        )
        body = intervals_route_to_segment_add(
            route, ride_id, title=config.title
        )
        title = body["title"]
        report(f"Uploading segment {title!r}…")
        segment_id = segment_add(session, headers, body)
        if segment_id:
            report(f"✓ Uploaded {title} (id {segment_id})")
            result.uploaded = 1
            result.uploaded_map[route_key] = segment_id
            live_ids.add(segment_id)
        else:
            report(f"✗ Failed to upload {title}.")
            result.failed = 1

    for key, segment_id in config.uploaded_segments.items():
        if key in result.uploaded_map:
            continue
        if segment_id not in live_ids:
            result.pruned_keys.append(key)

    return result
