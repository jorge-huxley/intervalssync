"""Bryton Active → intervals.icu sync orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import requests

from ..intervals_icu import (
    fetch_uploaded_external_ids,
    set_activity_type,
    upload_fit_file,
)
from .api import download_fit_to_path
from .ddp import DEFAULT_HOST, BrytonSession, list_activities, login
from .exceptions import BrytonSyncError

ACTIVITY_TYPE_KEEP = ""


def external_id_for(activity_id: str) -> str:
    return f"bryton_{activity_id}"


@dataclass
class Activity:
    activity_id: str
    title: str
    start_time: int


@dataclass
class SyncResult:
    listed: int = 0
    downloaded: int = 0
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0
    activities: list[Activity] = field(default_factory=list)


Progress = Callable[[str], None]


def _noop(_message: str) -> None:
    pass


def _activity_date_range(activities: list[Activity]) -> tuple[date, date]:
    dates: list[date] = []
    for act in activities:
        try:
            dates.append(datetime.fromtimestamp(act.start_time, tz=timezone.utc).date())
        except (TypeError, ValueError, OSError):
            continue
    if not dates:
        today = date.today()
        return today - timedelta(days=365), today + timedelta(days=1)
    return min(dates) - timedelta(days=1), max(dates) + timedelta(days=1)


@dataclass
class SyncConfig:
    bryton_email: str
    bryton_password: str
    intervals_api_key: str | None
    host: str = DEFAULT_HOST
    max_activities: int = 5
    download_dir: Path = Path("downloads")
    delete_after_upload: bool = True
    force_resync: bool = False
    activity_type: str = ACTIVITY_TYPE_KEEP
    list_activities: bool = True
    download_fit: bool = True
    upload_intervals: bool = True


def _to_activity(doc: dict) -> Activity:
    activity_id = doc.get("_id", "")
    return Activity(
        activity_id=activity_id,
        title=doc.get("name") or doc.get("title") or f"Bryton {activity_id}",
        start_time=int(doc.get("local_start_time") or 0),
    )


def sync(config: SyncConfig, progress: Progress | None = None) -> SyncResult:
    """Download recent Bryton rides and upload to intervals.icu."""
    report = progress or _noop
    result = SyncResult()

    report("Logging in to Bryton Active…")
    session = login(config.bryton_email, config.bryton_password, host=config.host)
    report("Logged in.")

    raw_activities = list_activities(session, limit=config.max_activities)
    activities = [_to_activity(doc) for doc in raw_activities]
    result.activities = activities
    result.listed = len(activities)

    if config.list_activities:
        report(f"Found {len(activities)} activities.")
        for act in activities:
            report(f"  • {act.activity_id} | {act.start_time} | {act.title}")

    if not (config.download_fit or config.upload_intervals):
        return result

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

    download_dir = Path(config.download_dir)

    for act in activities:
        ext = external_id_for(act.activity_id)
        fit_path = download_dir / f"{ext}.fit"

        if config.upload_intervals and ext in already_uploaded:
            report(f"↷ Skipping {act.activity_id} — already on intervals.icu.")
            result.skipped += 1
            continue

        if config.download_fit or config.upload_intervals:
            report(f"Downloading {act.activity_id}…")
            try:
                download_fit_to_path(act.activity_id, session, fit_path)
            except (requests.RequestException, ValueError) as exc:
                report(f"⚠ Could not download FIT for {act.activity_id}: {exc}")
                result.failed += 1
                continue
            result.downloaded += 1

        if config.upload_intervals:
            if not config.intervals_api_key:
                raise BrytonSyncError("intervals.icu API key is required for upload.")

            activity_id = upload_fit_file(
                fit_path, act.title, ext, config.intervals_api_key
            )
            if activity_id:
                report(f"✓ Uploaded {act.activity_id}: {act.title}")
                result.uploaded += 1
                if config.activity_type:
                    if set_activity_type(
                        activity_id, config.activity_type, config.intervals_api_key
                    ):
                        report(f"↻ Set {act.activity_id} → {config.activity_type}")
                    else:
                        report(f"⚠ Could not set activity type for {act.activity_id}.")
            else:
                report(f"✗ Failed to upload {act.activity_id}.")
                result.failed += 1
                continue

            if config.delete_after_upload:
                fit_path.unlink(missing_ok=True)
                report(f"  Removed local file {fit_path.name}")

    return result
