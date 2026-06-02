"""Pure sync logic for moving activities from iGPSPORT to intervals.icu.

This module contains no UI and no module-level side effects — it is driven by
the CLI and the GUI alike. Progress is surfaced through a callback so each
front-end can render it however it likes.

Flow (see CLAUDE.md for the full API notes):
  1. Log in to iGPSPORT; the `loginToken` cookie is URL-decoded and reused as a
     Bearer token for the gateway API.
  2. List activities (PascalCase keys: RideId / Title / StartTime).
  3. Resolve the FIT download URL: try queryActivityDetail, fall back to
     getDownloadUrl.
  4. Download the .fit file and upload it to intervals.icu (basic auth with the
     literal username "API_KEY").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

import requests

from .dropbox_client import (
    DEFAULT_DROPBOX_FOLDER,
    list_dropbox_ride_ids,
    upload_to_dropbox,
)

LOGIN_URL = "https://i.igpsport.com/Auth/Login"
ACTIVITY_LIST_URL = "https://i.igpsport.com/Activity/ActivityList"
GATEWAY = "https://prod.en.igpsport.com/service/web-gateway/web-analyze/activity"
INTERVALS_UPLOAD_URL = "https://intervals.icu/api/v1/athlete/0/activities"
INTERVALS_ACTIVITIES_URL = "https://intervals.icu/api/v1/athlete/0/activities"
INTERVALS_ACTIVITY_URL = "https://intervals.icu/api/v1/activity"

# iGPSPORT reports activity start times as "YYYY-MM-DD HH:MM:SS".
IGP_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# iGPSPORT exports every ride as the generic "Ride". intervals.icu doesn't take
# a sport on upload, so we PUT the desired type afterwards. An empty activity
# type means "leave the uploaded sport untouched" (do nothing). Any non-empty
# value — including "Ride" — is applied via PUT.
ACTIVITY_TYPE_KEEP = ""

# Cycling subset of the intervals.icu SportInfo enum (api_value, label). The API
# does NOT validate the string, so only ever send values from this list.
CYCLING_ACTIVITY_TYPES: list[tuple[str, str]] = [
    ("Ride", "Ride"),
    ("MountainBikeRide", "Mountain Bike Ride"),
    ("GravelRide", "Gravel Ride"),
    ("VirtualRide", "Virtual Ride"),
    ("EBikeRide", "E-Bike Ride"),
    ("EMountainBikeRide", "E-Mountain Bike Ride"),
    ("TrackRide", "Track Ride"),
    ("Cyclocross", "Cyclocross"),
    ("Handcycle", "Handcycle"),
    ("Velomobile", "Velomobile"),
]


def external_id_for(ride_id: int) -> str:
    """The intervals.icu external_id we assign to an iGPSPORT ride."""
    return f"igpsport_{ride_id}"


class SyncError(Exception):
    """Base class for errors the front-ends can show as friendly messages."""


class AuthError(SyncError):
    """Raised when iGPSPORT login fails or returns no usable token."""


@dataclass
class Activity:
    ride_id: int
    title: str
    start_time: str


@dataclass
class SyncResult:
    listed: int = 0
    downloaded: int = 0
    uploaded: int = 0
    uploaded_dropbox: int = 0
    skipped: int = 0
    skipped_dropbox: int = 0
    failed: int = 0
    failed_dropbox: int = 0
    activities: list[Activity] = field(default_factory=list)


# A progress callback receives short, human-readable status events. It is
# optional everywhere; the default is a no-op so core stays silent by itself.
Progress = Callable[[str], None]


def _noop(_message: str) -> None:
    pass


def login(session: requests.Session, user: str, password: str) -> dict[str, str]:
    """Authenticate and return auth headers carrying the Bearer token.

    The token is taken from the `loginToken` session cookie and URL-decoded —
    this cookie-to-Bearer step is required for the gateway endpoints.
    """
    resp = session.post(LOGIN_URL, json={"username": user, "password": password})
    if not resp.ok:
        raise AuthError(f"iGPSPORT login failed: HTTP {resp.status_code}")

    token = session.cookies.get("loginToken")
    if not token:
        raise AuthError("iGPSPORT login did not return a loginToken cookie")

    return {"Authorization": f"Bearer {unquote(token)}"}


def list_activities(session: requests.Session, max_activities: int) -> list[Activity]:
    """Return the most recent activities, newest first, capped at max_activities.

    ActivityList paginates: with no params it returns only the first page (10).
    The endpoint honours pageSize, so we ask for the full page in one request
    (pageNo navigation is unreliable). The slice is a safety belt in case the
    server ever returns more than we asked for.
    """
    resp = session.get(ACTIVITY_LIST_URL, params={"pageNo": 1, "pageSize": max_activities})
    resp.raise_for_status()

    items = resp.json().get("item", [])[:max_activities]
    activities: list[Activity] = []
    for item in items:
        ride_id = item["RideId"]
        activities.append(
            Activity(
                ride_id=ride_id,
                title=item.get("Title") or f"iGPSPORT {ride_id}",
                start_time=item.get("StartTime") or item.get("StartDate") or "unknown date",
            )
        )
    return activities


def resolve_fit_url(
    session: requests.Session, auth_headers: dict[str, str], ride_id: int
) -> str | None:
    """Resolve a FIT download URL: try queryActivityDetail, then getDownloadUrl."""
    detail = session.get(
        f"{GATEWAY}/queryActivityDetail/{ride_id}", headers=auth_headers
    )
    if detail.ok:
        fit_url = detail.json().get("data", {}).get("fitUrl")
        if fit_url:
            return fit_url

    fallback = session.get(
        f"{GATEWAY}/getDownloadUrl/{ride_id}", headers=auth_headers
    )
    if fallback.ok:
        return fallback.json().get("data")

    return None


def download_fit(fit_url: str, dest_path: Path) -> Path:
    """Download a .fit file to dest_path and return the path."""
    resp = requests.get(fit_url)
    resp.raise_for_status()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(resp.content)
    return dest_path


def upload_to_intervals(
    fit_path: Path, title: str, ride_id: int, api_key: str
) -> str | None:
    """Upload a .fit file to intervals.icu; return the new activity id or None.

    Uses basic auth with the literal username "API_KEY"; `external_id` reuses
    the iGPSPORT ride id so re-uploads are idempotent. The id is read from the
    UploadResponse so the caller can set the activity type afterwards.
    """
    with fit_path.open("rb") as f:
        resp = requests.post(
            INTERVALS_UPLOAD_URL,
            params={"name": title, "external_id": external_id_for(ride_id)},
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
    """Set an activity's sport on intervals.icu (e.g. "MountainBikeRide")."""
    resp = requests.put(
        f"{INTERVALS_ACTIVITY_URL}/{activity_id}",
        json={"type": activity_type},
        auth=("API_KEY", api_key),
    )
    return resp.ok


def fetch_uploaded_external_ids(
    api_key: str, oldest: date, newest: date
) -> set[str]:
    """Return the set of `external_id`s already on intervals.icu in a date range.

    The activity list endpoint includes the `external_id` we set at upload time,
    so we can tell which iGPSPORT rides are already present without re-downloading.
    """
    resp = requests.get(
        INTERVALS_ACTIVITIES_URL,
        params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        auth=("API_KEY", api_key),
    )
    resp.raise_for_status()
    return {a["external_id"] for a in resp.json() if a.get("external_id")}


def _activity_date_range(activities: list[Activity]) -> tuple[date, date]:
    """Date window covering the activities, padded a day each side.

    Falls back to a wide window if start times can't be parsed.
    """
    dates: list[date] = []
    for act in activities:
        try:
            dates.append(datetime.strptime(act.start_time, IGP_TIME_FORMAT).date())
        except (ValueError, TypeError):
            continue

    if not dates:
        today = date.today()
        return today - timedelta(days=365), today + timedelta(days=1)

    return min(dates) - timedelta(days=1), max(dates) + timedelta(days=1)


@dataclass
class SyncConfig:
    igp_user: str
    igp_password: str
    intervals_api_key: str | None
    dropbox_refresh_token: str | None = None
    dropbox_app_key: str | None = None
    max_activities: int = 5
    download_dir: Path = Path("downloads")
    delete_after_upload: bool = True
    # When False (default), skip activities already uploaded to intervals.icu.
    # When True, re-download and re-upload them regardless.
    force_resync: bool = False
    # Sport to set on uploaded activities (intervals.icu doesn't accept it on
    # upload). Empty string = leave the uploaded sport untouched.
    activity_type: str = ACTIVITY_TYPE_KEEP
    list_activities: bool = True
    get_download_url: bool = False
    download_fit: bool = False
    upload_intervals: bool = False
    upload_dropbox: bool = False
    dropbox_folder: str = DEFAULT_DROPBOX_FOLDER


def sync(config: SyncConfig, progress: Progress | None = None) -> SyncResult:
    """Run the configured steps end-to-end, reporting progress via the callback."""
    report = progress or _noop
    result = SyncResult()

    session = requests.Session()
    report("Logging in to iGPSPORT…")
    auth_headers = login(session, config.igp_user, config.igp_password)
    report("Logged in.")

    activities = list_activities(session, config.max_activities)
    result.activities = activities
    result.listed = len(activities)

    if config.list_activities:
        report(f"Found {len(activities)} activities.")
        for act in activities:
            report(f"  • {act.ride_id} | {act.start_time} | {act.title}")

    needs_url = (
        config.get_download_url
        or config.download_fit
        or config.upload_intervals
        or config.upload_dropbox
    )
    if not needs_url:
        return result

    # Figure out which activities are already on intervals.icu so we can skip
    # re-downloading them. Only relevant when uploading and not forcing a resync.
    already_uploaded: set[str] = set()
    if config.upload_intervals and not config.force_resync and config.intervals_api_key:
        oldest, newest = _activity_date_range(activities)
        try:
            already_uploaded = fetch_uploaded_external_ids(
                config.intervals_api_key, oldest, newest
            )
            report(
                f"{len(already_uploaded)} activities already on intervals.icu "
                "in this date range."
            )
        except requests.RequestException as exc:
            report(f"⚠ Could not check intervals.icu (will process all): {exc}")

    # Validate Dropbox prerequisites once, before processing any activity, so a
    # misconfiguration fails fast instead of part-way through the loop.
    dropbox_uploaded_ids: set[int] = set()
    if config.upload_dropbox:
        if not config.dropbox_app_key:
            raise SyncError("Dropbox app key is required for Dropbox upload.")
        if not config.dropbox_refresh_token:
            raise SyncError("Connect Dropbox in Settings before syncing.")

        # Skip-tracking for Dropbox is independent of intervals.icu: list the
        # ride ids already present in the folder so we don't re-upload them.
        if not config.force_resync:
            try:
                dropbox_uploaded_ids = list_dropbox_ride_ids(
                    config.dropbox_folder,
                    config.dropbox_refresh_token,
                    config.dropbox_app_key,
                )
                report(f"{len(dropbox_uploaded_ids)} activities already in Dropbox.")
            except Exception as exc:  # noqa: BLE001 — non-fatal; process all
                report(f"⚠ Could not check Dropbox (will process all): {exc}")

    download_dir = Path(config.download_dir)

    any_upload_enabled = config.upload_intervals or config.upload_dropbox

    for act in activities:
        ext = external_id_for(act.ride_id)
        fit_path = download_dir / f"{ext}.fit"

        # Each target tracks its own "already there" state, so an activity can
        # be uploaded to one target while being skipped on the other.
        intervals_needs_it = config.upload_intervals and ext not in already_uploaded
        dropbox_needs_it = (
            config.upload_dropbox and act.ride_id not in dropbox_uploaded_ids
        )

        if config.upload_intervals and not intervals_needs_it:
            report(f"↷ Skipping {act.ride_id} — already on intervals.icu.")
            result.skipped += 1
        if config.upload_dropbox and not dropbox_needs_it:
            report(f"↷ Skipping {act.ride_id} — already in Dropbox.")
            result.skipped_dropbox += 1

        # Nothing left to do once every enabled upload target already has it.
        if any_upload_enabled and not intervals_needs_it and not dropbox_needs_it:
            continue

        fit_url = resolve_fit_url(session, auth_headers, act.ride_id)
        if not fit_url:
            report(f"⚠ Could not resolve FIT URL for {act.ride_id}; skipping.")
            result.failed += 1
            continue

        if config.get_download_url and not (
            config.download_fit or config.upload_intervals or config.upload_dropbox
        ):
            report(f"FIT URL for {act.ride_id}: {fit_url}")
            continue

        report(f"Downloading {act.ride_id}…")
        download_fit(fit_url, fit_path)
        result.downloaded += 1

        intervals_ok = True
        if intervals_needs_it:
            if not config.intervals_api_key:
                raise SyncError("intervals.icu API key is required for upload.")

            activity_id = upload_to_intervals(
                fit_path, act.title, act.ride_id, config.intervals_api_key
            )
            if activity_id:
                report(f"✓ Uploaded {act.ride_id}: {act.title}")
                result.uploaded += 1

                if config.activity_type:
                    if set_activity_type(
                        activity_id, config.activity_type, config.intervals_api_key
                    ):
                        report(f"↻ Set {act.ride_id} → {config.activity_type}")
                    else:
                        report(f"⚠ Could not set activity type for {act.ride_id}.")
            else:
                report(f"✗ Failed to upload {act.ride_id}.")
                result.failed += 1
                intervals_ok = False

        dropbox_ok = True
        if dropbox_needs_it:
            report(f"Uploading {act.ride_id} to Dropbox…")
            try:
                upload_to_dropbox(
                    fit_path,
                    act.ride_id,
                    config.dropbox_refresh_token,
                    config.dropbox_app_key,
                    config.dropbox_folder,
                )
            except Exception as exc:  # noqa: BLE001 — surface provider failures
                dropbox_ok = False
                result.failed_dropbox += 1
                report(f"⚠ Dropbox upload failed for {act.ride_id}: {exc}")
            else:
                result.uploaded_dropbox += 1
                report(f"✓ Uploaded {act.ride_id} to Dropbox")

        # Remove the local file only once every enabled target is satisfied, so
        # a failure on either target keeps the file for a later retry.
        if config.delete_after_upload and any_upload_enabled and intervals_ok and dropbox_ok:
            fit_path.unlink(missing_ok=True)
            report(f"  Removed local file {fit_path.name}")

    return result
