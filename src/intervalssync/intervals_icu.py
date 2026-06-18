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


@dataclass
class CalendarWorkout:
    event_id: int
    name: str
    description: str
    activity_type: str
    workout_doc: dict[str, Any]


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def fetch_sport_settings_max_hr(
    api_key: str,
    sport: str,
    *,
    http: requests.Session | None = None,
) -> float | None:
    """Return athlete max HR (bpm) from intervals.icu sport settings."""
    client = http or requests.Session()
    resp = client.get(
        f"{INTERVALS_SPORT_SETTINGS_URL}/{sport}",
        auth=("API_KEY", api_key),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        return None
    return _num(data.get("max_hr"))
