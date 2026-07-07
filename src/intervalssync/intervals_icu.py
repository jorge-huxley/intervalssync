"""Shared intervals.icu API helpers.

Activity upload/dedup, calendar workout fetch, and sport-settings lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests

INTERVALS_UPLOAD_URL = "https://intervals.icu/api/v1/athlete/0/activities"
INTERVALS_ACTIVITIES_URL = "https://intervals.icu/api/v1/athlete/0/activities"
INTERVALS_ACTIVITY_URL = "https://intervals.icu/api/v1/activity"
INTERVALS_EVENTS_URL = "https://intervals.icu/api/v1/athlete/0/events"
INTERVALS_SPORT_SETTINGS_URL = "https://intervals.icu/api/v1/athlete/0/sport-settings"
INTERVALS_ROUTES_URL = "https://intervals.icu/api/v1/athlete/0/routes"


@dataclass
class CalendarWorkout:
    event_id: int
    name: str
    description: str
    activity_type: str
    workout_doc: dict[str, Any]


@dataclass(frozen=True)
class IntervalsRoute:
    route_id: int
    name: str
    distance: float | None
    activity_count: int
    latlngs: list[list[float]]
    most_recent_id: str | None
    description: str = ""


@dataclass(frozen=True)
class SportSettings:
    ftp: float | None
    lthr: float | None
    max_hr: float | None
    power_zones: list[float]
    hr_zones: list[float]


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    out: list[float] = []
    for item in value:
        num = _num(item)
        if num is not None:
            out.append(num)
    return out


def upload_fit_file(
    fit_path: Path, title: str, external_id: str, api_key: str
) -> str | None:
    """Upload a .fit file; return the new activity id or None on failure."""
    with fit_path.open("rb") as f:
        resp = requests.post(
            INTERVALS_UPLOAD_URL,
            params={"name": title, "external_id": external_id},
            files={"file": (fit_path.name, f, "application/octet-stream")},
            auth=("API_KEY", api_key),
        )
    if resp.status_code not in (200, 201):
        return None

    data = resp.json()
    activities = data.get("activities") or []
    if activities and activities[0].get("id"):
        return activities[0]["id"]
    return data.get("id")


def set_activity_type(activity_id: str, activity_type: str, api_key: str) -> bool:
    """Set an activity's sport on intervals.icu."""
    resp = requests.put(
        f"{INTERVALS_ACTIVITY_URL}/{activity_id}",
        json={"type": activity_type},
        auth=("API_KEY", api_key),
    )
    return resp.ok


def fetch_uploaded_external_ids(
    api_key: str, oldest: date, newest: date
) -> set[str]:
    """Return external_ids already on intervals.icu in a date range."""
    resp = requests.get(
        INTERVALS_ACTIVITIES_URL,
        params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        auth=("API_KEY", api_key),
    )
    resp.raise_for_status()
    return {a["external_id"] for a in resp.json() if a.get("external_id")}


def fetch_calendar_workouts(
    api_key: str,
    oldest: date,
    newest: date,
    *,
    http: requests.Session | None = None,
) -> list[CalendarWorkout]:
    """Fetch planned workouts from the intervals.icu calendar."""
    client = http or requests.Session()
    resp = client.get(
        INTERVALS_EVENTS_URL,
        params={
            "category": "WORKOUT",
            "resolve": "true",
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat(),
        },
        auth=("API_KEY", api_key),
        timeout=30,
    )
    resp.raise_for_status()
    workouts: list[CalendarWorkout] = []
    for event in resp.json():
        if event.get("category") != "WORKOUT":
            continue
        workout_doc = event.get("workout_doc")
        if not isinstance(workout_doc, dict):
            continue
        workouts.append(
            CalendarWorkout(
                event_id=int(event["id"]),
                name=str(event.get("name") or "Workout"),
                description=str(event.get("description") or ""),
                activity_type=str(event.get("type") or "Ride"),
                workout_doc=workout_doc,
            )
        )
    return workouts


def fetch_sport_settings(
    api_key: str,
    sport: str = "Ride",
    *,
    http: requests.Session | None = None,
) -> SportSettings:
    """Return athlete thresholds and zone definitions from intervals.icu sport settings."""
    client = http or requests.Session()
    resp = client.get(
        f"{INTERVALS_SPORT_SETTINGS_URL}/{sport}",
        auth=("API_KEY", api_key),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        return SportSettings(None, None, None, [], [])
    return SportSettings(
        ftp=_num(data.get("ftp")),
        lthr=_num(data.get("lthr")),
        max_hr=_num(data.get("max_hr")),
        power_zones=_num_list(data.get("power_zones")),
        hr_zones=_num_list(data.get("hr_zones")),
    )


def _parse_route(data: dict[str, Any]) -> IntervalsRoute | None:
    route_id = data.get("route_id")
    if route_id is None:
        return None
    latlngs_raw = data.get("latlngs")
    latlngs: list[list[float]] = []
    if isinstance(latlngs_raw, list):
        for point in latlngs_raw:
            if isinstance(point, list) and len(point) >= 2:
                latlngs.append([float(point[0]), float(point[1])])
    return IntervalsRoute(
        route_id=int(route_id),
        name=str(data.get("name") or f"Route {route_id}"),
        distance=_num(data.get("distance")),
        activity_count=int(data.get("activity_count") or 0),
        latlngs=latlngs,
        most_recent_id=(
            str(data["most_recent_id"]) if data.get("most_recent_id") else None
        ),
        description=str(data.get("description") or ""),
    )


def fetch_routes(
    api_key: str,
    *,
    http: requests.Session | None = None,
) -> list[IntervalsRoute]:
    """List clustered routes for the authenticated athlete."""
    client = http or requests.Session()
    resp = client.get(
        INTERVALS_ROUTES_URL,
        auth=("API_KEY", api_key),
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        return []
    routes: list[IntervalsRoute] = []
    for item in payload:
        if isinstance(item, dict):
            route = _parse_route(item)
            if route is not None:
                routes.append(route)
    return routes


def fetch_route(
    api_key: str,
    route_id: int,
    *,
    http: requests.Session | None = None,
) -> IntervalsRoute:
    """Fetch one route by id (includes latlngs polyline)."""
    client = http or requests.Session()
    resp = client.get(
        f"{INTERVALS_ROUTES_URL}/{route_id}",
        auth=("API_KEY", api_key),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected route response for route_id={route_id}")
    route = _parse_route(data)
    if route is None:
        raise ValueError(f"Route {route_id} missing route_id in response")
    return route


def fetch_activity_external_id(
    api_key: str,
    activity_id: str,
    *,
    http: requests.Session | None = None,
) -> str | None:
    """Return external_id for an intervals.icu activity, if set."""
    client = http or requests.Session()
    resp = client.get(
        f"{INTERVALS_ACTIVITY_URL}/{activity_id}",
        auth=("API_KEY", api_key),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        return None
    external_id = data.get("external_id")
    return str(external_id) if external_id else None


def fetch_sport_settings_max_hr(
    api_key: str,
    sport: str,
    *,
    http: requests.Session | None = None,
) -> float | None:
    """Return athlete max HR (bpm) from intervals.icu sport settings."""
    return fetch_sport_settings(api_key, sport, http=http).max_hr
