"""Shared intervals.icu API helpers.

Activity upload/dedup, calendar workout fetch, and sport-settings lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import isfinite
from pathlib import Path
from typing import Any

import requests

INTERVALS_UPLOAD_URL = "https://intervals.icu/api/v1/athlete/0/activities"
INTERVALS_ACTIVITIES_URL = "https://intervals.icu/api/v1/athlete/0/activities"
INTERVALS_ACTIVITY_URL = "https://intervals.icu/api/v1/activity"
INTERVALS_EVENTS_URL = "https://intervals.icu/api/v1/athlete/0/events"
INTERVALS_SPORT_SETTINGS_URL = "https://intervals.icu/api/v1/athlete/0/sport-settings"
INTERVALS_ATHLETE_URL = "https://intervals.icu/api/v1/athlete/0"


@dataclass
class CalendarWorkout:
    event_id: int
    name: str
    description: str
    activity_type: str
    workout_doc: dict[str, Any]
    start_date: str = ""


@dataclass(frozen=True)
class ActivityUploadResult:
    activity_id: str
    created: bool


@dataclass
class ActivityIdentities:
    activity_ids: set[str]
    external_ids: dict[str, str]


@dataclass(frozen=True)
class SportSettings:
    ftp: float | None
    lthr: float | None
    max_hr: float | None
    power_zones: list[float]
    hr_zones: list[float]
    power_zone_names: list[str] = field(default_factory=list)
    hr_zone_names: list[str] = field(default_factory=list)
    invalid_fields: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AthleteSettings:
    resting_hr: int | None
    weight: float | None
    height_cm: int | None
    birth_date: str | None
    sex: int | None
    invalid_fields: frozenset[str] = field(default_factory=frozenset)


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


def _source_num(data: dict[str, Any], key: str) -> tuple[float | None, bool]:
    value = data.get(key)
    if value is None:
        return None, False
    if isinstance(value, bool):
        return None, True
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, True
    if not isfinite(number) or number <= 0:
        return None, True
    return number, False


def _source_num_list(data: dict[str, Any], key: str) -> tuple[list[float], bool]:
    value = data.get(key)
    if value is None:
        return [], False
    if not isinstance(value, list) or not value:
        return [], True
    numbers: list[float] = []
    for item in value:
        if isinstance(item, bool):
            return [], True
        try:
            number = float(item)
        except (TypeError, ValueError):
            return [], True
        if not isfinite(number) or number <= 0:
            return [], True
        numbers.append(number)
    return numbers, False


def _source_names(data: dict[str, Any], key: str) -> tuple[list[str], bool]:
    value = data.get(key)
    if value is None:
        return [], False
    if not isinstance(value, list) or not value:
        return [], True
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return [], True
        names.append(item.strip())
    return names, False


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _parse_activity_id(value: Any) -> str | None:
    """Return a normalized Intervals identifier or None for unsupported values."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def upload_fit_file(
    fit_path: Path, title: str, external_id: str, api_key: str
) -> ActivityUploadResult | None:
    """Upload a .fit file and classify whether Intervals created or linked it."""
    with fit_path.open("rb") as f:
        resp = requests.post(
            INTERVALS_UPLOAD_URL,
            params={"name": title, "external_id": external_id},
            files={"file": (fit_path.name, f, "application/octet-stream")},
            auth=("API_KEY", api_key),
        )
    if resp.status_code not in (200, 201):
        return None

    try:
        data = resp.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    activities = data.get("activities") or []
    activity_id = None
    if (
        isinstance(activities, list)
        and activities
        and isinstance(activities[0], dict)
    ):
        activity_id = _parse_activity_id(activities[0].get("id"))
    if activity_id is None:
        activity_id = _parse_activity_id(data.get("id"))
    if activity_id is None:
        return None
    return ActivityUploadResult(
        activity_id=activity_id,
        created=resp.status_code == 201,
    )


def set_activity_type(activity_id: str, activity_type: str, api_key: str) -> bool:
    """Set an activity's sport on intervals.icu."""
    resp = requests.put(
        f"{INTERVALS_ACTIVITY_URL}/{activity_id}",
        json={"type": activity_type},
        auth=("API_KEY", api_key),
    )
    return resp.ok


def fetch_activity_identities(
    api_key: str, oldest: date, newest: date
) -> ActivityIdentities:
    """Return Intervals activity IDs and external-ID links in a date range."""
    resp = requests.get(
        INTERVALS_ACTIVITIES_URL,
        params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        auth=("API_KEY", api_key),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError("intervals.icu activities response must be a list")
    activity_ids: set[str] = set()
    external_ids: dict[str, str] = {}
    for activity in data:
        if not isinstance(activity, dict) or "id" not in activity:
            continue
        activity_id = _parse_activity_id(activity["id"])
        if activity_id is None:
            raise ValueError("intervals.icu activity id must be a nonempty string")
        activity_ids.add(activity_id)
        external_id = activity.get("external_id")
        if external_id is not None:
            external_id = _parse_activity_id(external_id)
            if external_id is None:
                raise ValueError("intervals.icu external_id must be a nonempty string")
            external_ids[external_id] = activity_id
    return ActivityIdentities(activity_ids, external_ids)


def fetch_uploaded_external_ids(
    api_key: str, oldest: date, newest: date
) -> set[str]:
    """Return external_ids already on intervals.icu in a date range."""
    return set(fetch_activity_identities(api_key, oldest, newest).external_ids)


def activity_exists(api_key: str, activity_id: str) -> bool:
    """Return whether an activity exists, raising if absence cannot be verified."""
    resp = requests.get(
        f"{INTERVALS_ACTIVITY_URL}/{activity_id}",
        auth=("API_KEY", api_key),
        timeout=30,
    )
    if resp.status_code == 404:
        return False
    if resp.status_code == 200:
        return True
    resp.raise_for_status()
    raise requests.HTTPError(
        f"Unexpected HTTP {resp.status_code} verifying activity {activity_id}",
        response=resp,
    )


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
                start_date=str(event.get("start_date_local") or "")[:10],
            )
        )
    return workouts


def fetch_sport_settings(
    api_key: str,
    sport: str = "Ride",
    *,
    http: requests.Session | None = None,
    strict: bool = False,
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
        if strict:
            raise ValueError("intervals.icu sport settings response must be an object")
        return SportSettings(None, None, None, [], [])
    if not strict:
        return SportSettings(
            ftp=_num(data.get("ftp")),
            lthr=_num(data.get("lthr")),
            max_hr=_num(data.get("max_hr")),
            power_zones=_num_list(data.get("power_zones")),
            hr_zones=_num_list(data.get("hr_zones")),
        )
    invalid: set[str] = set()
    ftp, ftp_invalid = _source_num(data, "ftp")
    lthr, lthr_invalid = _source_num(data, "lthr")
    max_hr, max_hr_invalid = _source_num(data, "max_hr")
    # Preserve fractional thresholds; each consumer applies its legacy rounding.
    power_zones, power_invalid = _source_num_list(data, "power_zones")
    hr_zones, hr_invalid = _source_num_list(data, "hr_zones")
    power_names, power_names_invalid = _source_names(data, "power_zone_names")
    hr_names, hr_names_invalid = _source_names(data, "hr_zone_names")
    for key, is_invalid in (
        ("ftp", ftp_invalid),
        ("lthr", lthr_invalid),
        ("max_hr", max_hr_invalid),
        ("power_zones", power_invalid),
        ("hr_zones", hr_invalid),
        ("power_zone_names", power_names_invalid),
        ("hr_zone_names", hr_names_invalid),
    ):
        if is_invalid:
            invalid.add(key)
    return SportSettings(
        ftp=ftp,
        lthr=lthr,
        max_hr=max_hr,
        power_zones=power_zones,
        hr_zones=hr_zones,
        power_zone_names=power_names,
        hr_zone_names=hr_names,
        invalid_fields=frozenset(invalid),
    )


def fetch_sport_settings_max_hr(
    api_key: str,
    sport: str,
    *,
    http: requests.Session | None = None,
) -> float | None:
    """Return athlete max HR (bpm) from intervals.icu sport settings."""
    return fetch_sport_settings(api_key, sport, http=http).max_hr


def fetch_athlete_weight(
    api_key: str,
    *,
    http: requests.Session | None = None,
) -> float | None:
    """Return athlete weight in kg from intervals.icu (`icu_weight`, else `weight`)."""
    client = http or requests.Session()
    resp = client.get(
        INTERVALS_ATHLETE_URL,
        auth=("API_KEY", api_key),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        return None
    return _num(data.get("icu_weight")) or _num(data.get("weight"))


def fetch_athlete_settings(
    api_key: str,
    *,
    http: requests.Session | None = None,
) -> AthleteSettings:
    """Return normalized rider fields without deriving values from activities."""
    client = http or requests.Session()
    resp = client.get(
        INTERVALS_ATHLETE_URL,
        auth=("API_KEY", api_key),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("intervals.icu athlete response must be an object")

    invalid: set[str] = set()

    resting_value, resting_invalid = _source_num(data, "icu_resting_hr")
    resting_hr: int | None = None
    if resting_value is not None:
        if resting_value.is_integer():
            resting_hr = int(resting_value)
        else:
            resting_invalid = True
    if resting_invalid:
        invalid.add("resting_hr")

    weight_key = "icu_weight" if data.get("icu_weight") is not None else "weight"
    weight, weight_invalid = _source_num(data, weight_key)
    if weight_invalid:
        invalid.add("weight")

    height, height_invalid = _source_num(data, "height")
    height_cm: int | None = None
    if height is not None:
        if height <= 3:
            try:
                height_cm = _round_half_up(Decimal(str(height)) * Decimal("100"))
            except (InvalidOperation, ValueError):
                height_invalid = True
        else:
            height_invalid = True
    if height_invalid:
        invalid.add("height")

    birth_value = data.get("icu_date_of_birth")
    birth_date: str | None = None
    birth_invalid = False
    if birth_value is not None:
        if isinstance(birth_value, str):
            try:
                birth_date = date.fromisoformat(birth_value.strip()).isoformat()
            except ValueError:
                birth_invalid = True
        else:
            birth_invalid = True
    if birth_invalid:
        invalid.add("birth_date")

    sex_value = data.get("sex")
    sex: int | None = None
    sex_invalid = False
    if sex_value is not None:
        normalized_sex = str(sex_value).strip().casefold()
        if normalized_sex in {"m", "male"}:
            sex = 1
        elif normalized_sex in {"f", "female"}:
            sex = 2
        else:
            sex_invalid = True
    if sex_invalid:
        invalid.add("sex")

    return AthleteSettings(
        resting_hr=resting_hr,
        weight=weight,
        height_cm=height_cm,
        birth_date=birth_date,
        sex=sex,
        invalid_fields=frozenset(invalid),
    )
