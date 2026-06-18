"""Bryton Active → intervals.icu sync orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import requests

from ..dropbox_client import (
    DEFAULT_DROPBOX_FOLDER,
    list_dropbox_fit_names,
    upload_to_dropbox,
)
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


def dropbox_filename_for(activity: "Activity", use_date: bool = True) -> str:
    """Return the Dropbox filename for a Bryton activity."""
    fallback = f"{external_id_for(activity.activity_id)}.fit"
    if not use_date:
        return fallback
    try:
        if activity.start_time <= 0:
            raise ValueError("missing start time")
        start = datetime.fromtimestamp(activity.start_time)
    except (TypeError, ValueError, OSError):
        return fallback
    return f"{start:%y%m%d%H%M%S}.fit"


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
    uploaded_dropbox: int = 0
    skipped: int = 0
    skipped_dropbox: int = 0
    failed: int = 0
    failed_dropbox: int = 0
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
    dropbox_refresh_token: str | None = None
    dropbox_app_key: str | None = None
    host: str = DEFAULT_HOST
    max_activities: int = 5
    download_dir: Path = Path("downloads")
    delete_after_upload: bool = True
    force_resync: bool = False
    activity_type: str = ACTIVITY_TYPE_KEEP
    list_activities: bool = True
    download_fit: bool = True
    upload_intervals: bool = True
    upload_dropbox: bool = False
    dropbox_folder: str = DEFAULT_DROPBOX_FOLDER
    dropbox_date_filenames: bool = True


def _to_activity(doc: dict) -> Activity:
    activity_id = doc.get("_id", "")
    return Activity(
        activity_id=activity_id,
        title=doc.get("name") or doc.get("title") or f"Bryton {activity_id}",
        start_time=int(doc.get("local_start_time") or 0),
    )


def sync(config: SyncConfig, progress: Progress | None = None) -> SyncResult:
    """Download recent Bryton rides and upload to intervals.icu and/or Dropbox."""
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

    if not (config.download_fit or config.upload_intervals or config.upload_dropbox):
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

    dropbox_uploaded_names: set[str] = set()
    if config.upload_dropbox:
        if not config.dropbox_app_key:
            raise BrytonSyncError("Dropbox app key is required for Dropbox upload.")
        if not config.dropbox_refresh_token:
            raise BrytonSyncError("Connect Dropbox in Settings before syncing.")

        if not config.force_resync:
            try:
                dropbox_uploaded_names = list_dropbox_fit_names(
                    config.dropbox_folder,
                    config.dropbox_refresh_token,
                    config.dropbox_app_key,
                )
                report(f"{len(dropbox_uploaded_names)} activities already in Dropbox.")
            except Exception as exc:  # noqa: BLE001 — non-fatal; process all
                report(f"⚠ Could not check Dropbox (will process all): {exc}")

    download_dir = Path(config.download_dir)
    any_upload_enabled = config.upload_intervals or config.upload_dropbox

    for act in activities:
        ext = external_id_for(act.activity_id)
        fit_path = download_dir / f"{ext}.fit"
        dropbox_filename = dropbox_filename_for(act, config.dropbox_date_filenames)

        intervals_needs_it = config.upload_intervals and ext not in already_uploaded
        dropbox_needs_it = (
            config.upload_dropbox and dropbox_filename not in dropbox_uploaded_names
        )

        if config.upload_intervals and not intervals_needs_it:
            report(f"↷ Skipping {act.activity_id} — already on intervals.icu.")
            result.skipped += 1
        if config.upload_dropbox and not dropbox_needs_it:
            report(f"↷ Skipping {act.activity_id} — already in Dropbox.")
            result.skipped_dropbox += 1

        if any_upload_enabled and not intervals_needs_it and not dropbox_needs_it:
            continue

        if config.download_fit or intervals_needs_it or dropbox_needs_it:
            report(f"Downloading {act.activity_id}…")
            try:
                download_fit_to_path(act.activity_id, session, fit_path)
            except (requests.RequestException, ValueError) as exc:
                report(f"⚠ Could not download FIT for {act.activity_id}: {exc}")
                result.failed += 1
                continue
            result.downloaded += 1

        intervals_ok = True
        if intervals_needs_it:
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
                intervals_ok = False

        dropbox_ok = True
        if dropbox_needs_it:
            report(f"Uploading {act.activity_id} to Dropbox…")
            try:
                upload_to_dropbox(
                    fit_path,
                    dropbox_filename,
                    config.dropbox_refresh_token,
                    config.dropbox_app_key,
                    config.dropbox_folder,
                )
            except Exception as exc:  # noqa: BLE001 — surface provider failures
                dropbox_ok = False
                result.failed_dropbox += 1
                report(f"⚠ Dropbox upload failed for {act.activity_id}: {exc}")
            else:
                result.uploaded_dropbox += 1
                report(f"✓ Uploaded {act.activity_id} to Dropbox")

        if config.delete_after_upload and any_upload_enabled and intervals_ok and dropbox_ok:
            fit_path.unlink(missing_ok=True)
            report(f"  Removed local file {fit_path.name}")

    return result
