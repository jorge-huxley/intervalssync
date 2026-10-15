"""Upload planned workouts from intervals.icu to iGPSPORT custom workouts.

Uses the mobile JSON API (EditCustomWorkOut), not FIT upload. Source data is
intervals.icu ``workout_doc`` from calendar events (see intervals.icu forum
guide on downloading planned workouts).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

import requests

from .. import intervals_icu
from .core import SyncError, login
from .http import HTTP_TIMEOUT
from .region import IgpRegionConfig, resolve_region

IGPS_API = "https://prod.en.igpsport.com"
IGPS_WORKOUT_LIST_URL = f"{IGPS_API}/service/mobile/api/WorkOut/CustomWorkout"
IGPS_WORKOUT_EDIT_URL = f"{IGPS_API}/service/mobile/api/WorkOut/EditCustomWorkOut"

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


class UnsupportedWorkoutError(ValueError):
    """The source workout has semantics this relay must not silently change."""


def _noop(_message: str) -> None:
    pass


@dataclass
class WorkoutUploadResult:
    listed: int = 0
    uploaded: int = 0
    updated: int = 0
    recreated: int = 0
    skipped: int = 0
    failed: int = 0
    no_steps: int = 0
    unsupported: int = 0
    verification_failed: int = 0
    description_truncated: int = 0
    uploaded_map: dict[str, int] = field(default_factory=dict)
    synced_map: dict[str, int] = field(default_factory=dict)
    workout_export_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    pruned_keys: list[str] = field(default_factory=list)


@dataclass
class WorkoutUploadConfig:
    igp_user: str
    igp_password: str
    intervals_api_key: str
    igp_region: str = "international"
    oldest: date | None = None
    newest: date | None = None
    workout_days_ahead: int = 1
    uploaded_workouts: dict[str, int] = field(default_factory=dict)
    workout_export_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    force_resync: bool = False
    checkpoint: Callable[[WorkoutUploadResult], None] | None = None


def list_custom_workouts(
    session: requests.Session,
    auth_headers: dict[str, str],
    page_index: int = 1,
    page_size: int = 20,
    region: IgpRegionConfig | str | None = None,
) -> dict[str, Any]:
    """Return the iGPSPORT custom-workout list response JSON."""
    cfg = resolve_region(region.name if isinstance(region, IgpRegionConfig) else region)
    resp = session.get(
        cfg.workout_list_url,
        params={"PageIndex": page_index, "PageSize": page_size},
        headers=auth_headers,
        timeout=HTTP_TIMEOUT,
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
    region: IgpRegionConfig | str | None = None,
) -> set[int]:
    """Return every custom-workout ID currently on iGPSPORT."""
    ids: set[int] = set()
    page_index = 1
    while True:
        data = list_custom_workouts(
            session, auth_headers, page_index, page_size, region=region
        )
        if not isinstance(data, dict) or data.get("code") != 0:
            raise SyncError("iGPSPORT returned an incomplete custom-workout list")
        payload = data.get("data")
        if not isinstance(payload, dict):
            raise SyncError("iGPSPORT custom-workout list has invalid data")
        items = payload.get("items")
        if not isinstance(items, list):
            raise SyncError("iGPSPORT custom-workout list has invalid items")
        if not items:
            break
        for item in items:
            if not isinstance(item, dict):
                raise SyncError("iGPSPORT custom-workout list has invalid item")
            workout_id = _workout_id_from_item(item)
            if workout_id is None or workout_id <= 0:
                raise SyncError("iGPSPORT custom-workout list has invalid ID")
            if workout_id in ids:
                raise SyncError("iGPSPORT custom-workout pagination repeated an ID")
            ids.add(workout_id)
        if len(items) < page_size:
            break
        page_index += 1
    return ids


def apply_uploaded_workout_map(
    uploaded_workouts: dict[str, int],
    result: WorkoutUploadResult,
) -> None:
    """Merge accepted IDs, including uploads still pending verification."""
    for event_id, state in result.workout_export_state.items():
        uploaded_workouts[event_id] = state["remote_id"]
    uploaded_workouts.update(result.uploaded_map)
    uploaded_workouts.update(result.synced_map)
    for key in result.pruned_keys:
        uploaded_workouts.pop(key, None)


def apply_workout_state(
    uploaded_workouts: dict[str, int],
    workout_export_state: dict[str, dict[str, Any]],
    result: WorkoutUploadResult,
) -> None:
    """Persist event metadata without rebuilding or discarding legacy mappings."""
    next_state = {
        str(key): dict(value) for key, value in result.workout_export_state.items()
    }
    apply_uploaded_workout_map(uploaded_workouts, result)
    workout_export_state.clear()
    workout_export_state.update(next_state)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def export_fingerprint(body: dict[str, Any]) -> str:
    """Hash the normalized remote export while ignoring generated UUIDs and id."""

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: normalize(child)
                for key, child in sorted(value.items())
                if key not in {"uuid", "id"}
            }
        if isinstance(value, list):
            return [normalize(child) for child in value]
        return value

    encoded = json.dumps(
        normalize(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return _digest(encoded)


def _has_skip_marker(workout: intervals_icu.CalendarWorkout) -> bool:
    text = f"{workout.name}\n{workout.description}".lower()
    return "[skip-igp]" in text


def _valid_export_state(value: Any, remote_id: int | None) -> dict[str, Any] | None:
    """Only trust export metadata belonging to the authoritative mapped ID."""
    if not isinstance(value, dict) or remote_id is None:
        return None
    if type(value.get("remote_id")) is not int or value["remote_id"] != remote_id:
        return None
    fingerprint = value.get("export_fingerprint")
    return {
        "remote_id": remote_id,
        "export_fingerprint": fingerprint if isinstance(fingerprint, str) else None,
        "verification_version": (
            1 if type(value.get("verification_version")) is int
            and value["verification_version"] == 1 else None
        ),
        "verification_status": (
            value.get("verification_status")
            if value.get("verification_status") in ("verified", "pending") else None
        ),
    }


def fetch_custom_workout_detail(
    session: requests.Session,
    auth_headers: dict[str, str],
    workout_id: int,
    region: IgpRegionConfig | str | None = None,
) -> dict[str, Any] | None:
    """Return a single iGPSPORT workout detail, or None for an invalid response."""
    cfg = resolve_region(region.name if isinstance(region, IgpRegionConfig) else region)
    response = session.get(
        f"{cfg.mobile_api_base}/WorkOut/GetWorkOutDetail",
        params={"id": workout_id},
        headers=auth_headers,
        timeout=HTTP_TIMEOUT,
    )
    if not response.ok:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    data = (
        payload.get("data")
        if isinstance(payload, dict) and payload.get("code") == 0
        else None
    )
    return data if isinstance(data, dict) else None


def _target_shape(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        key: value[key]
        for key in ("unit", "value", "minValue", "maxValue")
        if key in value
    }


def _structure_shape(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if not isinstance(value, list):
        return None
    result: list[dict[str, Any]] = []
    for step in value:
        if not isinstance(step, dict):
            return None
        shape = {
            key: step[key]
            for key in ("type", "intensityClass", "openDuration", "length")
            if key in step
        }
        for key in ("intensityTarget", "secondaryIntensityTarget"):
            if key in step:
                target = _target_shape(step[key])
                if target is None:
                    return None
                shape[key] = target
        if "steps" in step:
            nested = _structure_shape(step["steps"])
            if nested is None:
                return None
            shape["steps"] = nested
        result.append(shape)
    return result


def _verification_shape(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    structure = _structure_shape(data.get("structure"))
    if structure is None:
        return None
    return {"title": data.get("title"), "structure": structure}


def verify_custom_workout(
    session: requests.Session,
    auth_headers: dict[str, str],
    workout_id: int,
    expected_body: dict[str, Any],
    region: IgpRegionConfig | str | None = None,
) -> bool:
    """Read back and compare executable workout semantics after a write."""
    try:
        remote = fetch_custom_workout_detail(
            session, auth_headers, workout_id, region=region
        )
    except requests.RequestException:
        return False
    expected = _verification_shape(expected_body.get("data"))
    actual = _verification_shape(remote)
    return expected is not None and expected == actual


def upload_custom_workout(
    session: requests.Session,
    auth_headers: dict[str, str],
    body: dict[str, Any],
    region: IgpRegionConfig | str | None = None,
) -> int | None:
    """Create or update a custom workout; return workoutId on success."""
    cfg = resolve_region(region.name if isinstance(region, IgpRegionConfig) else region)
    resp = session.post(
        cfg.workout_edit_url,
        json=body,
        headers=auth_headers,
        timeout=HTTP_TIMEOUT,
    )
    if not resp.ok:
        return None
    data = resp.json()
    if data.get("code") != 0:
        return None
    payload = data.get("data") or {}
    workout_id = payload.get("workoutId")
    if isinstance(workout_id, bool) or not isinstance(workout_id, (str, int)):
        return None
    try:
        parsed_id = int(workout_id)
    except ValueError:
        return None
    return parsed_id if parsed_id > 0 else None


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


def _integer(value: Any, *, field: str, positive: bool = False) -> int:
    number = _num(value)
    if number is None or not number.is_integer() or (positive and number <= 0):
        qualifier = "a positive whole number" if positive else "a whole number"
        raise UnsupportedWorkoutError(f"{field} must be {qualifier}")
    return int(number)


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
            "unit": "PercentOfFtp",
            "value": 0,
            "minValue": min_v,
            "maxValue": max_v,
        }
    if units not in {"w", "watt", "watts"}:
        raise UnsupportedWorkoutError(f"unsupported power units: {units or 'missing'}")
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
                "value": 0,
                "minValue": int(min_v),
                "maxValue": int(max_v),
            }
        if value is not None:
            if 1 <= value <= 5 and value == int(value):
                return {"unit": "HeartRate", "value": int(value)}
            return {
                "unit": "HeartRateCustom",
                "value": 0,
                "minValue": int(value),
                "maxValue": int(value),
            }

    hr = step.get("hr")
    if not isinstance(hr, dict):
        return None
    units = str(hr.get("units") or "").lower()
    value = _num(hr.get("value"))
    start = _num(hr.get("start"))
    end = _num(hr.get("end"))
    if units == "hr_zone":
        if value is None or value != int(value) or not 1 <= value <= 5:
            raise UnsupportedWorkoutError("heart-rate zone must be an integer from 1 to 5")
        return {"unit": "HeartRate", "value": int(value)}
    if units not in {"bpm", "heart_rate"}:
        raise UnsupportedWorkoutError(
            f"unsupported heart-rate units: {units or 'missing'}"
        )
    if start is not None and end is not None:
        return {
            "unit": "HeartRateCustom",
            "value": 0,
            "minValue": int(start),
            "maxValue": int(end),
        }
    if value is not None:
        if 1 <= value <= 5 and value == int(value):
            return {"unit": "HeartRate", "value": int(value)}
        return {
            "unit": "HeartRateCustom",
            "value": 0,
            "minValue": int(value),
            "maxValue": int(value),
        }
    return None


def _map_cadence_target(step: dict[str, Any]) -> dict[str, Any] | None:
    cadence = step.get("cadence")
    if not isinstance(cadence, dict):
        return None
    units = str(cadence.get("units") or "").lower()
    if units not in {"rpm", ""}:
        raise UnsupportedWorkoutError(f"unsupported cadence units: {units}")
    value = _num(cadence.get("value"))
    start = _num(cadence.get("start"))
    end = _num(cadence.get("end"))
    min_v = start if start is not None else value
    max_v = end if end is not None else value
    if min_v is None and max_v is None:
        return None
    min_v = int(min_v if min_v is not None else max_v)
    max_v = int(max_v if max_v is not None else min_v)
    return {
        "unit": "Cadence",
        "value": 0,
        "minValue": min_v,
        "maxValue": max_v,
    }


def _workout_target(workout_doc: dict[str, Any]) -> str:
    raw_target = workout_doc.get("target")
    if raw_target is None or str(raw_target).strip() == "":
        return "AUTO"
    target = str(raw_target).upper()
    if target in {"AUTO", "POWER", "HR"}:
        return target
    raise UnsupportedWorkoutError(f"unsupported workout target: {target}")


def _primary_target(step: dict[str, Any], target: str) -> dict[str, Any] | None:
    if target == "POWER":
        return _map_power_target(step)
    if target == "HR":
        return _map_hr_target(step)

    has_power = isinstance(step.get("power"), dict) or isinstance(
        step.get("_power"), dict
    )
    has_hr = isinstance(step.get("hr"), dict) or isinstance(step.get("_hr"), dict)
    if has_power and has_hr:
        raise UnsupportedWorkoutError("ambiguous automatic power and heart-rate targets")
    if has_power:
        return _map_power_target(step)
    if has_hr:
        return _map_hr_target(step)
    return None


def _assert_supported_step(step: dict[str, Any], target: str) -> None:
    for field in ("ramp", "freeride", "maxeffort"):
        if step.get(field):
            raise UnsupportedWorkoutError(f"unsupported step feature: {field}")
    if isinstance(step.get("pace"), dict):
        raise UnsupportedWorkoutError("pace targets are not supported")
    if step.get("calories") is not None or step.get("calorie") is not None:
        raise UnsupportedWorkoutError("calorie duration is not supported")
    has_power = any(isinstance(step.get(key), dict) for key in ("power", "_power"))
    has_hr = any(isinstance(step.get(key), dict) for key in ("hr", "_hr"))
    if target == "POWER" and (
        isinstance(step.get("hr"), dict) or (has_hr and not has_power)
    ):
        raise UnsupportedWorkoutError("secondary heart-rate targets are not supported")
    if target == "HR" and (
        isinstance(step.get("power"), dict) or (has_power and not has_hr)
    ):
        raise UnsupportedWorkoutError("secondary power targets are not supported")
    if isinstance(step.get("secondary_hr"), dict):
        raise UnsupportedWorkoutError("secondary heart-rate targets are not supported")


def _step_length(step: dict[str, Any]) -> dict[str, Any]:
    if step.get("distance") is not None:
        return {
            "unit": "Meter",
            "value": _integer(step["distance"], field="distance", positive=True),
        }
    if step.get("duration") is None:
        raise UnsupportedWorkoutError("step has neither duration nor distance")
    return {
        "unit": "Second",
        "value": _integer(step["duration"], field="duration", positive=True),
    }


def _map_icu_step(step: dict[str, Any], index: int, target: str) -> dict[str, Any] | None:
    _assert_supported_step(step, target)
    reps = step.get("reps")
    nested = step.get("steps")
    if reps is not None:
        repetitions = _integer(reps, field="repetitions", positive=True)
        if not isinstance(nested, list) or not nested:
            raise UnsupportedWorkoutError("repetition has no valid child steps")
        child_steps = []
        for i, child in enumerate(nested, start=1):
            if not isinstance(child, dict):
                raise UnsupportedWorkoutError("repetition contains an invalid step")
            mapped = _map_icu_step(child, i, target)
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
            "length": {"unit": "Repetition", "value": repetitions},
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
        igp_step["length"] = _step_length(step)

    primary_target = _primary_target(step, target)
    if primary_target:
        igp_step["intensityTarget"] = primary_target

    cadence_target = _map_cadence_target(step)
    if cadence_target:
        if primary_target is None:
            raise UnsupportedWorkoutError("cadence requires a supported primary target")
        igp_step["secondaryIntensityTarget"] = cadence_target

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

    target = _workout_target(workout_doc)
    structure: list[dict[str, Any]] = []
    for i, step in enumerate(raw_steps, start=1):
        if not isinstance(step, dict):
            raise UnsupportedWorkoutError("workout contains an invalid step")
        mapped = _map_icu_step(step, i, target)
        if mapped is not None:
            structure.append(mapped)

    if not structure:
        return None

    doc_description = str(description or workout_doc.get("description") or "")
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
    """Export workouts using exact event-ID mappings and content fingerprints."""
    report = progress or _noop
    result = WorkoutUploadResult()
    today = date.today()
    oldest = config.oldest or today
    newest = config.newest or (
        today + timedelta(days=max(1, config.workout_days_ahead) - 1)
    )
    report("Logging in to iGPSPORT…")
    session = requests.Session()
    region = resolve_region(config.igp_region)
    auth_headers = login(session, config.igp_user, config.igp_password, region)
    report("Logged in.")
    try:
        live_ids = fetch_all_custom_workout_ids(session, auth_headers, region=region)
    except (requests.RequestException, ValueError) as exc:
        raise SyncError("Could not list iGPSPORT workouts") from exc
    report(f"Found {len(live_ids)} custom workouts on iGPSPORT.")
    report("Fetching planned workouts from intervals.icu…")
    try:
        calendar = intervals_icu.fetch_calendar_workouts(
            config.intervals_api_key, oldest, newest
        )
    except (requests.RequestException, ValueError) as exc:
        raise SyncError("Could not fetch intervals.icu workouts") from exc
    if not isinstance(calendar, list):
        raise SyncError("intervals.icu workouts response must be a list")
    current_events = {str(item.event_id) for item in calendar}
    if len(current_events) != len(calendar):
        raise SyncError("intervals.icu calendar has ambiguous event IDs")
    result.listed = len(calendar)
    report(f"Found {len(calendar)} planned workouts.")

    mapping: dict[str, int] = {}
    for event_id, raw_id in config.uploaded_workouts.items():
        if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
            continue
        try:
            remote_id = int(raw_id)
        except ValueError:
            continue
        if remote_id > 0:
            mapping[str(event_id)] = remote_id
    states: dict[str, dict[str, Any]] = {}
    for event_id, value in config.workout_export_state.items():
        state = _valid_export_state(value, mapping.get(str(event_id)))
        if state is not None:
            states[str(event_id)] = state
    result.workout_export_state = states

    for item in calendar:
        event_id = str(item.event_id)
        if item.activity_type not in _CYCLING_TYPES:
            report(f"↷ Skipping {item.name} — unsupported type (cycling only in v1).")
            result.skipped += 1
            continue
        if _has_skip_marker(item):
            report(f"↷ Skipping {item.name} — [skip-igp] is present.")
            result.skipped += 1
            continue
        stored_id = mapping.get(event_id)
        on_remote = stored_id is not None and stored_id in live_ids
        try:
            body = icu_workout_doc_to_igps(
                item.name, item.description, item.workout_doc,
                existing_workout_id=stored_id if on_remote else None,
            )
        except UnsupportedWorkoutError as exc:
            report(f"⚠ Skipping {item.name} — unsupported workout: {exc}.")
            result.unsupported += 1
            result.failed += 1
            continue
        if body is None:
            report(f"⚠ Skipping {item.name} — no structured steps.")
            result.no_steps += 1
            continue
        description = str(item.description or item.workout_doc.get("description") or "")
        if len(description) > 500:
            result.description_truncated += 1
        fingerprint = export_fingerprint(body)
        state = states.get(event_id)
        unchanged = (
            on_remote and state is not None
            and state["export_fingerprint"] == fingerprint
            and not config.force_resync
        )
        if unchanged:
            if state["verification_version"] == 1 and state["verification_status"] == "verified":
                report(f"↷ Skipping {item.name} — export is unchanged.")
                result.skipped += 1
                continue
            if verify_custom_workout(session, auth_headers, stored_id, body, region=region):
                state["verification_version"] = 1
                state["verification_status"] = "verified"
                result.synced_map[event_id] = stored_id
                result.skipped += 1
            else:
                result.verification_failed += 1
                result.failed += 1
                report(f"✗ Could not verify export for {item.name}.")
            continue

        action = "update" if on_remote else ("recreate" if stored_id else "upload")
        report(f"{action.capitalize()} {item.name}…")
        accepted_id = upload_custom_workout(session, auth_headers, body, region=region)
        if accepted_id is None or (action == "update" and accepted_id != stored_id):
            report(f"✗ Failed to {action} {item.name} with the expected ID.")
            result.failed += 1
            continue
        mapping[event_id] = accepted_id
        live_ids.add(accepted_id)
        states[event_id] = {
            "remote_id": accepted_id,
            "export_fingerprint": None,
            "verification_version": None,
            "verification_status": "pending",
        }
        # Save the accepted ID before any further network operation. A failed
        # read-back must not make the next run create a duplicate.
        if config.checkpoint:
            try:
                config.checkpoint(result)
            except Exception as exc:  # noqa: BLE001
                raise SyncError("Could not checkpoint accepted workout ID") from exc
        if not verify_custom_workout(session, auth_headers, accepted_id, body, region=region):
            report(f"✗ Could not verify iGPSPORT export for {item.name}.")
            result.verification_failed += 1
            result.failed += 1
            continue
        states[event_id].update(
            export_fingerprint=fingerprint,
            verification_version=1,
            verification_status="verified",
        )
        if action == "update":
            result.updated += 1
        elif action == "recreate":
            result.recreated += 1
        else:
            result.uploaded += 1
            result.uploaded_map[event_id] = accepted_id
        result.synced_map[event_id] = accepted_id

    # Only complete cloud observations justify forgetting historical mappings.
    for event_id, remote_id in mapping.items():
        if event_id not in current_events and remote_id not in live_ids:
            result.pruned_keys.append(event_id)
            states.pop(event_id, None)
    return result
