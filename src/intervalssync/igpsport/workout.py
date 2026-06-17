"""Upload planned workouts from intervals.icu to iGPSPORT custom workouts.

Uses the mobile JSON API (EditCustomWorkOut), not FIT upload. Source data is
intervals.icu ``workout_doc`` from calendar events (see intervals.icu forum
guide on downloading planned workouts).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

import requests

from .core import SyncError, login

IGPS_API = "https://prod.en.igpsport.com"
IGPS_WORKOUT_LIST_URL = f"{IGPS_API}/service/mobile/api/WorkOut/CustomWorkout"
IGPS_WORKOUT_EDIT_URL = f"{IGPS_API}/service/mobile/api/WorkOut/EditCustomWorkOut"
INTERVALS_EVENTS_URL = "https://intervals.icu/api/v1/athlete/0/events"

# intervals.icu cycling types we accept in v1.
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


def _noop(_message: str) -> None:
    pass


@dataclass
class CalendarWorkout:
    event_id: int
    name: str
    description: str
    activity_type: str
    workout_doc: dict[str, Any]


@dataclass
class WorkoutUploadResult:
    listed: int = 0
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0
    no_steps: int = 0
    uploaded_map: dict[str, int] = field(default_factory=dict)
    pruned_keys: list[str] = field(default_factory=list)


@dataclass
class WorkoutUploadConfig:
    igp_user: str
    igp_password: str
    intervals_api_key: str
    oldest: date | None = None
    newest: date | None = None
    workout_days_ahead: int = 1
    uploaded_workouts: dict[str, int] = field(default_factory=dict)
    force_resync: bool = False


def list_custom_workouts(
    session: requests.Session,
    auth_headers: dict[str, str],
    page_index: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """Return the iGPSPORT custom-workout list response JSON."""
    resp = session.get(
        IGPS_WORKOUT_LIST_URL,
        params={"PageIndex": page_index, "PageSize": page_size},
        headers=auth_headers,
    )
    resp.raise_for_status()
    return resp.json()


def _workout_id_from_item(item: dict[str, Any]) -> int | None:
    for key in ("workoutId", "id", "workout_id"):
        value = item.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


def fetch_all_custom_workout_ids(
    session: requests.Session,
    auth_headers: dict[str, str],
    *,
    page_size: int = 50,
) -> set[int]:
    """Return every custom-workout ID currently on iGPSPORT."""
    ids: set[int] = set()
    page_index = 1
    while True:
        data = list_custom_workouts(session, auth_headers, page_index, page_size)
        if data.get("code") != 0:
            break
        items = (data.get("data") or {}).get("items") or []
        if not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            workout_id = _workout_id_from_item(item)
            if workout_id is not None:
                ids.add(workout_id)
        if len(items) < page_size:
            break
        page_index += 1
    return ids


def apply_uploaded_workout_map(
    uploaded_workouts: dict[str, int],
    result: WorkoutUploadResult,
) -> None:
    """Merge upload results into config and drop entries for deleted workouts."""
    uploaded_workouts.update(result.uploaded_map)
    for key in result.pruned_keys:
        uploaded_workouts.pop(key, None)


def upload_custom_workout(
    session: requests.Session,
    auth_headers: dict[str, str],
    body: dict[str, Any],
) -> int | None:
    """Create or update a custom workout; return workoutId on success."""
    resp = session.post(IGPS_WORKOUT_EDIT_URL, json=body, headers=auth_headers)
    if not resp.ok:
        return None
    data = resp.json()
    if data.get("code") != 0:
        return None
    payload = data.get("data") or {}
    workout_id = payload.get("workoutId")
    return int(workout_id) if workout_id is not None else None


def fetch_calendar_workouts(
    api_key: str,
    oldest: date,
    newest: date,
) -> list[CalendarWorkout]:
    """Fetch planned workouts from the intervals.icu calendar."""
    resp = requests.get(
        INTERVALS_EVENTS_URL,
        params={
            "category": "WORKOUT",
            "resolve": "true",
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat(),
        },
        auth=("API_KEY", api_key),
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


def _step_name(step: dict[str, Any], index: int) -> str:
    text = str(step.get("text") or "").strip()
    if text:
        return text[:64]
    return f"Step {index}"


def _intensity_class(step: dict[str, Any]) -> str:
    intensity = str(step.get("intensity") or "").lower()
    if step.get("warmup") or intensity == "warmup":
        return "WarmUp"
    if step.get("cooldown") or intensity == "cooldown":
        return "CoolDown"
    if intensity in ("rest", "recovery"):
        return "Rest"
    return "Active"


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _map_power_target(step: dict[str, Any]) -> dict[str, Any] | None:
    resolved = step.get("_power")
    if isinstance(resolved, dict):
        start = _num(resolved.get("start"))
        end = _num(resolved.get("end"))
        value = _num(resolved.get("value"))
        min_v = start if start is not None else value
        max_v = end if end is not None else value
        if min_v is None and max_v is None:
            return None
        min_v = int(min_v if min_v is not None else max_v)
        max_v = int(max_v if max_v is not None else min_v)
        if min_v > max_v:
            min_v, max_v = max_v, min_v
        return {
            "unit": "PowerCustom",
            "value": 0,
            "minValue": min_v,
            "maxValue": max_v,
        }

    power = step.get("power")
    if not isinstance(power, dict):
        return None

    units = str(power.get("units") or "").lower()
    start = _num(power.get("start"))
    end = _num(power.get("end"))
    value = _num(power.get("value"))
    min_v = start if start is not None else value
    max_v = end if end is not None else value
    if min_v is None and max_v is None:
        return None
    min_v = int(min_v if min_v is not None else max_v)
    max_v = int(max_v if max_v is not None else min_v)
    if min_v > max_v:
        min_v, max_v = max_v, min_v

    if units == "%ftp":
        return {
            "unit": "PercentOfFTP",
            "minValue": min_v,
            "maxValue": max_v,
        }
    return {
        "unit": "PowerCustom",
        "value": 0,
        "minValue": min_v,
        "maxValue": max_v,
    }


def _map_hr_target(step: dict[str, Any]) -> dict[str, Any] | None:
    resolved = step.get("_hr")
    if isinstance(resolved, dict):
        start = _num(resolved.get("start"))
        end = _num(resolved.get("end"))
        value = _num(resolved.get("value"))
        min_v = start if start is not None else value
        max_v = end if end is not None else value
        if min_v is not None and max_v is not None:
            return {
                "unit": "HeartRateCustom",
                "minValue": int(min_v),
                "maxValue": int(max_v),
            }
        if value is not None:
            if 1 <= value <= 5 and value == int(value):
                return {"unit": "HeartRate", "value": int(value)}
            return {
                "unit": "HeartRateCustom",
                "minValue": int(value),
                "maxValue": int(value),
            }

    hr = step.get("hr")
    if not isinstance(hr, dict):
        return None
    value = _num(hr.get("value"))
    start = _num(hr.get("start"))
    end = _num(hr.get("end"))
    if start is not None and end is not None:
        return {
            "unit": "HeartRateCustom",
            "minValue": int(start),
            "maxValue": int(end),
        }
    if value is not None:
        if 1 <= value <= 5 and value == int(value):
            return {"unit": "HeartRate", "value": int(value)}
        return {
            "unit": "HeartRateCustom",
            "minValue": int(value),
            "maxValue": int(value),
        }
    return None


def _map_cadence_target(step: dict[str, Any]) -> dict[str, Any] | None:
    cadence = step.get("cadence")
    if not isinstance(cadence, dict):
        return None
    value = _num(cadence.get("value"))
    start = _num(cadence.get("start"))
    end = _num(cadence.get("end"))
    min_v = start if start is not None else value
    max_v = end if end is not None else value
    if min_v is None and max_v is None:
        return None
    min_v = int(min_v if min_v is not None else max_v)
    max_v = int(max_v if max_v is not None else min_v)
    return {"unit": "Cadence", "minValue": min_v, "maxValue": max_v}


def _map_icu_step(step: dict[str, Any], index: int) -> dict[str, Any] | None:
    reps = step.get("reps")
    nested = step.get("steps")
    if reps and isinstance(nested, list) and nested:
        child_steps = []
        for i, child in enumerate(nested, start=1):
            if not isinstance(child, dict):
                continue
            mapped = _map_icu_step(child, i)
            if mapped is not None:
                child_steps.append(mapped)
        if not child_steps:
            return None
        return {
            "type": "Repetition",
            "name": _step_name(step, index),
            "uuid": str(uuid.uuid4()),
            "intensityClass": "Active",
            "openDuration": "false",
            "length": {"unit": "Repetition", "value": int(reps)},
            "steps": child_steps,
        }

    open_duration = bool(step.get("until_lap_press"))
    igp_step: dict[str, Any] = {
        "type": "Step",
        "name": _step_name(step, index),
        "uuid": str(uuid.uuid4()),
        "intensityClass": _intensity_class(step),
        "openDuration": "true" if open_duration else "false",
    }

    if not open_duration:
        duration = step.get("duration")
        if duration is None:
            return None
        igp_step["length"] = {"unit": "Second", "value": int(duration)}

    power_target = _map_power_target(step)
    if power_target:
        igp_step["intensityTarget"] = power_target
    else:
        hr_target = _map_hr_target(step)
        if hr_target:
            igp_step["intensityTarget"] = hr_target

    cadence_target = _map_cadence_target(step)
    if cadence_target:
        igp_step["cadenceTarget"] = cadence_target

    return igp_step


def _total_time(structure: list[dict[str, Any]], workout_doc: dict[str, Any]) -> int:
    doc_duration = workout_doc.get("duration")
    if isinstance(doc_duration, int) and doc_duration > 0:
        return doc_duration
    if isinstance(doc_duration, float) and doc_duration > 0:
        return int(doc_duration)

    total = 0

    def walk(steps: list[dict[str, Any]], repeat: int = 1) -> None:
        nonlocal total
        for step in steps:
            if step.get("type") == "Repetition":
                reps = step.get("length", {}).get("value", 1)
                nested = step.get("steps") or []
                walk(nested, repeat * int(reps))
            elif step.get("openDuration") != "true":
                length = step.get("length") or {}
                if length.get("unit") == "Second":
                    total += int(length.get("value", 0)) * repeat

    walk(structure)
    return total


def icu_workout_doc_to_igps(
    name: str,
    description: str,
    workout_doc: dict[str, Any],
    *,
    existing_workout_id: int | None = None,
) -> dict[str, Any] | None:
    """Map intervals.icu workout_doc to an EditCustomWorkOut request body."""
    raw_steps = workout_doc.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None

    structure: list[dict[str, Any]] = []
    for i, step in enumerate(raw_steps, start=1):
        if not isinstance(step, dict):
            continue
        mapped = _map_icu_step(step, i)
        if mapped is not None:
            structure.append(mapped)

    if not structure:
        return None

    doc_description = str(workout_doc.get("description") or description or "")
    data: dict[str, Any] = {
        "title": name[:64],
        "description": doc_description[:500],
        "totalTime": _total_time(structure, workout_doc),
        "workoutType": "bike",
        "sportBigType": 1,
        "allowDeletion": True,
        "structure": structure,
    }
    if existing_workout_id:
        data["id"] = str(existing_workout_id)

    return {"data": data}


def upload_workouts(
    config: WorkoutUploadConfig,
    progress: Progress | None = None,
) -> WorkoutUploadResult:
    """Fetch upcoming intervals.icu workouts and push them to iGPSPORT."""
    report = progress or _noop
    result = WorkoutUploadResult()

    today = date.today()
    oldest = config.oldest or today
    days = max(1, config.workout_days_ahead)
    newest = config.newest or (today + timedelta(days=days - 1))

    report("Logging in to iGPSPORT…")
    session = requests.Session()
    auth_headers = login(session, config.igp_user, config.igp_password)
    report("Logged in.")

    live_ids = fetch_all_custom_workout_ids(session, auth_headers)
    report(f"Found {len(live_ids)} custom workouts on iGPSPORT.")

    report("Fetching planned workouts from intervals.icu…")
    try:
        calendar = fetch_calendar_workouts(config.intervals_api_key, oldest, newest)
    except requests.RequestException as exc:
        raise SyncError(f"Could not fetch intervals.icu workouts: {exc}") from exc

    result.listed = len(calendar)
    report(f"Found {len(calendar)} planned workouts.")

    for workout in calendar:
        event_key = str(workout.event_id)

        if workout.activity_type not in _CYCLING_TYPES:
            report(
                f"↷ Skipping {workout.name} — unsupported type "
                f"{workout.activity_type!r} (cycling only in v1)."
            )
            result.skipped += 1
            continue

        stored_id = config.uploaded_workouts.get(event_key)
        on_igpsport = stored_id is not None and stored_id in live_ids

        if on_igpsport and not config.force_resync:
            report(f"↷ Skipping {workout.name} — already on iGPSPORT.")
            result.skipped += 1
            continue

        update_id = stored_id if config.force_resync and on_igpsport else None
        body = icu_workout_doc_to_igps(
            workout.name,
            workout.description,
            workout.workout_doc,
            existing_workout_id=update_id,
        )
        if body is None:
            report(
                f"⚠ Skipping {workout.name} — no structured steps "
                "(open the workout in intervals.icu first)."
            )
            result.no_steps += 1
            continue

        report(f"Uploading {workout.name}…")
        workout_id = upload_custom_workout(session, auth_headers, body)
        if workout_id:
            report(f"✓ Uploaded {workout.name} (workoutId {workout_id})")
            result.uploaded += 1
            result.uploaded_map[event_key] = workout_id
            live_ids.add(workout_id)
        else:
            report(f"✗ Failed to upload {workout.name}.")
            result.failed += 1

    for event_key, workout_id in config.uploaded_workouts.items():
        if event_key in result.uploaded_map:
            continue
        if workout_id not in live_ids:
            result.pruned_keys.append(event_key)

    return result
