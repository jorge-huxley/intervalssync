"""Upload planned workouts from intervals.icu to Bryton Active (web FIT API).

Uses the Bryton Active website backend (active.brytonsport.com): map
intervals.icu ``workout_doc`` to Bryton-native FIT and POST multipart to
/workout/upload/{userId}.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable

import requests

from .. import intervals_icu
from .ddp import WEB_HOST, BrytonSession, call_method, login
from .exceptions import BrytonSyncError
from .fit_encode import bryton_hr_uses_mhr, icu_workout_doc_to_bryton_fit

_CYCLING_TYPES = frozenset(
    {
        "Ride",
        "MountainBikeRide",
        "GravelRide",
        "VirtualRide",
        "EBikeRide",
        "EMountainBikeRide",
        "TrackRide",
        "Cyclocross",
        "Handcycle",
        "Velomobile",
    }
)

Progress = Callable[[str], None]


def _steps_target_hr(steps: Any) -> bool:
    if not isinstance(steps, list):
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("hr") is not None:
            return True
        if _steps_target_hr(step.get("steps")):
            return True
    return False


def workout_doc_targets_hr(workout_doc: dict[str, Any]) -> bool:
    """Return True when intervals.icu workout_doc uses heart-rate targets."""
    target = str(workout_doc.get("target") or "").upper()
    if target == "HR":
        return True
    return _steps_target_hr(workout_doc.get("steps"))


def _noop(_message: str) -> None:
    pass


@dataclass
class BrytonWorkoutUploadResult:
    listed: int = 0
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0
    no_steps: int = 0
    uploaded_map: dict[str, str] = field(default_factory=dict)
    pruned_keys: list[str] = field(default_factory=list)


def _stored_on_bryton(stored: str | None, live_ids: set[str], live_names: set[str]) -> bool:
    if not stored:
        return False
    return stored in live_ids or stored in live_names


@dataclass
class BrytonWorkoutUploadConfig:
    bryton_email: str
    bryton_password: str
    intervals_api_key: str
    oldest: date | None = None
    newest: date | None = None
    workout_days_ahead: int = 1
    uploaded_workouts: dict[str, str] = field(default_factory=dict)
    force_resync: bool = False


def apply_uploaded_bryton_workout_map(
    uploaded_workouts: dict[str, str],
    result: BrytonWorkoutUploadResult,
) -> None:
    """Merge upload results into config and drop entries for deleted workouts."""
    uploaded_workouts.update(result.uploaded_map)
    for key in result.pruned_keys:
        uploaded_workouts.pop(key, None)


def _file_stem(name: str) -> str:
    stem = name[:-4] if name.lower().endswith(".fit") else name
    return stem.strip()


def _names_from_file_entry(entry: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(entry, str):
        names.add(_file_stem(entry))
        return names
    if not isinstance(entry, dict):
        return names
    for key in ("name", "filename", "title", "originalName"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            names.add(_file_stem(value))
    file_id = entry.get("_id") or entry.get("id")
    if isinstance(file_id, str) and file_id.strip():
        names.add(_file_stem(file_id))
    return names


def _ids_from_file_entry(entry: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(entry, str):
        ids.add(entry.strip())
        return ids
    if not isinstance(entry, dict):
        return ids
    for key in ("id", "_id"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            ids.add(value.strip())
    url = entry.get("url")
    if isinstance(url, str) and "/userFiles/" in url:
        parts = url.split("/userFiles/", 1)[-1].split("/")
        if parts and parts[0].strip():
            ids.add(parts[0].strip())
    return ids


def _parse_workout_list_result(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        workouts = result.get("workout")
        if isinstance(workouts, list):
            return [entry for entry in workouts if isinstance(entry, dict)]
    if isinstance(result, list):
        return [entry for entry in result if isinstance(entry, dict)]
    return []


def _fetch_workout_library(session: BrytonSession) -> tuple[set[str], set[str]]:
    """Return (file ids, known name stems) from Bryton's user.file.list."""
    result = call_method(session, "user.file.list", [])
    ids: set[str] = set()
    names: set[str] = set()
    for entry in _parse_workout_list_result(result):
        entry_ids = _ids_from_file_entry(entry)
        ids.update(entry_ids)
        names.update(_names_from_file_entry(entry))
        names.update(entry_ids)
    return ids, names


def list_workout_file_ids(session: BrytonSession) -> set[str]:
    """Return Bryton workout file ids currently in the user's library."""
    ids, _ = _fetch_workout_library(session)
    return ids


def list_workout_file_names(session: BrytonSession) -> set[str]:
    """Return workout file name stems currently in the Bryton library."""
    _, names = _fetch_workout_library(session)
    return names


def _sanitize_workout_filename(name: str, *, event_id: int) -> str:
    cleaned = re.sub(r"[^\w\-]+", "_", name.strip())
    cleaned = cleaned.strip("_")
    if not cleaned:
        cleaned = f"icu_{event_id}"
    return cleaned[:48]


def _auto_workout_filename() -> str:
    now = datetime.now()
    return (
        f"bsWO{now.month:02d}{now.day:02d}_"
        f"{now.hour:02d}{now.minute:02d}{now.second:02d}"
    )


def upload_workout_fit(
    session: BrytonSession,
    fit_bytes: bytes,
    name: str,
    *,
    http: requests.Session | None = None,
) -> bool:
    """Upload a FIT workout to Bryton Active web; return True on success."""
    stem = _file_stem(name) or _auto_workout_filename()
    filename = f"{stem}.fit"
    url = f"https://{session.host}/workout/upload/{session.user_id}"
    headers = {
        "X-User-Id": session.user_id,
        "X-Auth-Token": session.auth_token,
    }
    client = http or requests.Session()
    resp = client.post(
        url,
        files={"file": (filename, fit_bytes, "application/octet-stream")},
        data={"name": filename, "provider": "bryton"},
        headers=headers,
        timeout=120,
    )
    return resp.ok


def web_login(email: str, password: str) -> BrytonSession:
    """Log in to the Bryton Active website backend."""
    return login(email, password, host=WEB_HOST)


def upload_workouts(
    config: BrytonWorkoutUploadConfig,
    progress: Progress | None = None,
) -> BrytonWorkoutUploadResult:
    """Fetch upcoming intervals.icu workouts and push FIT files to Bryton."""
    report = progress or _noop
    result = BrytonWorkoutUploadResult()

    today = date.today()
    oldest = config.oldest or today
    days = max(1, config.workout_days_ahead)
    newest = config.newest or (today + timedelta(days=days - 1))

    report("Logging in to Bryton Active…")
    session = web_login(config.bryton_email, config.bryton_password)
    report("Logged in.")

    live_ids, live_names = _fetch_workout_library(session)
    report(f"Found {len(live_ids)} custom workouts on Bryton.")

    report("Fetching planned workouts from intervals.icu…")
    intervals_http = requests.Session()
    try:
        calendar = intervals_icu.fetch_calendar_workouts(
            config.intervals_api_key,
            oldest,
            newest,
            http=intervals_http,
        )
    except requests.RequestException as exc:
        raise BrytonSyncError(f"Could not fetch intervals.icu workouts: {exc}") from exc

    result.listed = len(calendar)
    report(f"Found {len(calendar)} planned workouts.")

    http = requests.Session()
    cached_max_hr: float | None = None
    max_hr_fetched = False
    for workout in calendar:
        event_key = str(workout.event_id)

        if workout.activity_type not in _CYCLING_TYPES:
            report(
                f"↷ Skipping {workout.name} — unsupported type "
                f"{workout.activity_type!r} (cycling only in v1)."
            )
            result.skipped += 1
            continue

        stored = config.uploaded_workouts.get(event_key)
        on_bryton = _stored_on_bryton(stored, live_ids, live_names)

        if on_bryton and not config.force_resync:
            report(f"↷ Skipping {workout.name} — already on Bryton.")
            result.skipped += 1
            continue

        ids_before = set(live_ids)

        encode_max_hr: float | None = None
        if bryton_hr_uses_mhr() and workout_doc_targets_hr(workout.workout_doc):
            if not max_hr_fetched:
                try:
                    cached_max_hr = intervals_icu.fetch_sport_settings_max_hr(
                        config.intervals_api_key,
                        workout.activity_type,
                        http=intervals_http,
                    )
                except requests.RequestException as exc:
                    raise BrytonSyncError(
                        f"Could not fetch intervals.icu max HR for {workout.activity_type}: {exc}"
                    ) from exc
                max_hr_fetched = True
            encode_max_hr = cached_max_hr

        fit_bytes = icu_workout_doc_to_bryton_fit(
            workout.name,
            workout.workout_doc,
            max_hr=encode_max_hr,
        )
        if fit_bytes is None:
            report(
                f"⚠ Skipping {workout.name} — no structured steps "
                "(open the workout in intervals.icu first)."
            )
            result.no_steps += 1
            continue

        upload_name = (
            stored
            if config.force_resync and on_bryton and stored
            else _auto_workout_filename()
        )

        report(f"Uploading {workout.name}…")
        if upload_workout_fit(session, fit_bytes, upload_name, http=http):
            after_ids, _ = _fetch_workout_library(session)
            new_ids = after_ids - ids_before
            stored_value = next(iter(new_ids), upload_name)
            report(f"✓ Uploaded {workout.name} ({upload_name}.fit)")
            result.uploaded += 1
            result.uploaded_map[event_key] = stored_value
            live_ids.add(stored_value)
            live_names.add(upload_name)
            live_names.add(_file_stem(upload_name))
        else:
            report(f"✗ Failed to upload {workout.name}.")
            result.failed += 1

    for event_key, stored_value in config.uploaded_workouts.items():
        if event_key in result.uploaded_map:
            continue
        if not _stored_on_bryton(stored_value, live_ids, live_names):
            result.pruned_keys.append(event_key)

    return result
