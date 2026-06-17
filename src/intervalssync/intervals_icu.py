"""Shared intervals.icu upload and deduplication helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import requests

INTERVALS_UPLOAD_URL = "https://intervals.icu/api/v1/athlete/0/activities"
INTERVALS_ACTIVITIES_URL = "https://intervals.icu/api/v1/athlete/0/activities"
INTERVALS_ACTIVITY_URL = "https://intervals.icu/api/v1/activity"


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
