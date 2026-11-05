"""Sync thresholds, zones, and weight from intervals.icu to iGPSPORT profile."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable

import requests

from .. import intervals_icu
from ..intervals_icu import AthleteSettings, SportSettings
from .core import SyncError, login
from .region import resolve_region
from .interval_info import (
    HEART_RATE_COMPUTE_MODE_MAX_HR,
    HEART_RATE_COMPUTE_MODE_HRR,
    HEART_RATE_COMPUTE_MODE_LTHR,
    build_personal_user_info_payload_updates,
    fetch_personal_interval_info,
    fetch_user_info,
    mobile_headers,
    member_id_from_token,
    profile_summary,
    update_personal_interval_info,
    update_personal_user_info,
    update_user_weight,
    zone_range_summary,
)
from .zone_map import map_hr_zones, map_power_zones

Progress = Callable[[str], None]


def _noop(_message: str) -> None:
    pass


@dataclass
class ProfileSyncConfig:
    igp_user: str
    igp_password: str
    intervals_api_key: str
    igp_region: str = "international"
    sport: str = "Ride"


@dataclass
class ProfileSyncResult:
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    weight_before: float | None = None
    weight_after: float | None = None


@dataclass
class ProfileThresholdStatus:
    needs_sync: bool
    differences: list[str]
    intervals_fingerprint: str
    intervals: dict[str, int | None]
    igpsport: dict[str, int | None]


SUPPORTED_RIDER_FIELDS = (
    "ftp",
    "power_zones",
    "max_hr",
    "lthr",
    "hr_zones",
    "resting_hr",
    "weight",
    "height",
    "birth_date",
    "sex",
)
_RIDER_DEPENDENCIES = {
    "power_zones": {"ftp"},
    "hr_zones": {"lthr", "max_hr"},
}
_INTERVAL_FIELDS = frozenset(
    {"ftp", "power_zones", "max_hr", "lthr", "hr_zones", "resting_hr"}
)
_PERSONAL_FIELDS = frozenset({"weight", "height", "birth_date", "sex"})
_FAILURE_STATUSES = frozenset({"invalid", "write_failed", "verify_failed"})


@dataclass(frozen=True)
class RiderFieldSelection:
    requested: tuple[str, ...]
    effective: tuple[str, ...]


@dataclass
class RiderSettingsPlan:
    selection: RiderFieldSelection
    interval_body: dict[str, Any]
    personal_payload: dict[str, Any]
    field_statuses: dict[str, str]
    interval_changed_fields: tuple[str, ...]
    personal_changed_fields: tuple[str, ...]
    source_values: dict[str, Any]
    current_values: dict[str, Any]
    desired_values: dict[str, Any]


@dataclass
class RiderSettingsSyncConfig:
    igp_user: str
    igp_password: str
    intervals_api_key: str
    igp_region: str = "international"
    sport: str = "Ride"
    fields: str | None = None
    dry_run: bool = False
    show_values: bool = False


@dataclass
class RiderSettingsSyncResult:
    requested_fields: tuple[str, ...]
    effective_fields: tuple[str, ...]
    field_statuses: dict[str, str]
    selected: int
    updated: int
    verified: int
    unchanged: int
    source_missing: int
    failed: int
    source_values: dict[str, Any] | None = None
    current_values: dict[str, Any] | None = None
    desired_values: dict[str, Any] | None = None


def parse_rider_fields(raw: str | None) -> RiderFieldSelection:
    """Validate a field list and expand dependencies in canonical order."""
    if raw is None or not raw.strip():
        return RiderFieldSelection(SUPPORTED_RIDER_FIELDS, SUPPORTED_RIDER_FIELDS)
    parts = [part.strip() for part in raw.split(",")]
    if any(not part for part in parts):
        raise ValueError("rider fields must not contain empty entries")
    if len(set(parts)) != len(parts):
        raise ValueError("rider fields must not contain duplicates")
    unknown = [part for part in parts if part not in SUPPORTED_RIDER_FIELDS]
    if unknown:
        raise ValueError(f"unsupported rider field: {unknown[0]}")
    requested_set = set(parts)
    effective_set = set(requested_set)
    for field_name in requested_set:
        effective_set.update(_RIDER_DEPENDENCIES.get(field_name, set()))
    requested = tuple(name for name in SUPPORTED_RIDER_FIELDS if name in requested_set)
    effective = tuple(name for name in SUPPORTED_RIDER_FIELDS if name in effective_set)
    return RiderFieldSelection(requested, effective)


def _one_decimal(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _zone_shape(zones: Any) -> tuple[tuple[Any, Any], ...]:
    if not isinstance(zones, list):
        return ()
    return tuple(
        (zone.get("start"), zone.get("end"))
        for zone in zones
        if isinstance(zone, dict)
    )


def _current_personal_value(user: dict[str, Any], field_name: str) -> Any:
    if field_name == "weight":
        value = user.get("weight")
        try:
            return _one_decimal(float(value)) if value is not None else None
        except (TypeError, ValueError):
            return None
    if field_name == "height":
        try:
            return int(user["height"]) if user.get("height") is not None else None
        except (TypeError, ValueError):
            return None
    if field_name == "birth_date":
        return user.get("birthDate") or None
    if field_name == "sex":
        value = user.get("gender")
        if value is None:
            value = user.get("sex")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
    raise ValueError(f"unsupported personal field: {field_name}")


def _hr_table_for_mode(mode: Any) -> str:
    try:
        normalized = int(mode)
    except (TypeError, ValueError):
        normalized = HEART_RATE_COMPUTE_MODE_MAX_HR
    return {
        HEART_RATE_COMPUTE_MODE_MAX_HR: "heartRate",
        HEART_RATE_COMPUTE_MODE_HRR: "heartRateReserve",
        HEART_RATE_COMPUTE_MODE_LTHR: "heartRateLactateThreshold",
    }.get(normalized, "heartRate")


def _interval_value(body: dict[str, Any], field_name: str) -> Any:
    member = body.get("member") if isinstance(body.get("member"), dict) else {}
    if field_name == "ftp":
        return member.get("ftp")
    if field_name == "max_hr":
        return member.get("mhr")
    if field_name == "lthr":
        return member.get("lthr")
    if field_name == "resting_hr":
        return member.get("quietHeartRate")
    if field_name == "power_zones":
        return _zone_shape(body.get("power"))
    if field_name == "hr_zones":
        mode = member.get("heartRateComputeMode")
        return (mode, _zone_shape(body.get(_hr_table_for_mode(mode))))
    raise ValueError(f"unsupported interval field: {field_name}")


def _set_status(
    field_name: str,
    source: Any,
    current: Any,
    desired: Any,
    *,
    statuses: dict[str, str],
    source_values: dict[str, Any],
    current_values: dict[str, Any],
    desired_values: dict[str, Any],
) -> None:
    source_values[field_name] = source
    current_values[field_name] = current
    desired_values[field_name] = desired
    statuses[field_name] = "unchanged" if current == desired else "would_update"


def build_rider_settings_plan(
    sport: SportSettings,
    athlete: AthleteSettings,
    current_interval: dict[str, Any],
    current_user: dict[str, Any],
    selection: RiderFieldSelection,
) -> RiderSettingsPlan:
    """Build a deterministic, non-mutating rider-settings synchronization plan."""
    interval_body = copy.deepcopy(current_interval)
    member = interval_body.get("member")
    if not isinstance(member, dict):
        raise SyncError("iGPSPORT profile payload has no member block")
    statuses: dict[str, str] = {}
    source_values: dict[str, Any] = {}
    current_values: dict[str, Any] = {}
    desired_values: dict[str, Any] = {}

    interval_sources = {
        "ftp": sport.ftp,
        "max_hr": sport.max_hr,
        "lthr": sport.lthr,
        "resting_hr": athlete.resting_hr,
    }
    interval_member_keys = {
        "ftp": "ftp",
        "max_hr": "mhr",
        "lthr": "lthr",
        "resting_hr": "quietHeartRate",
    }
    invalid_source_fields = set(sport.invalid_fields) | set(athlete.invalid_fields)

    for field_name in selection.effective:
        if field_name not in interval_sources:
            continue
        source = interval_sources[field_name]
        if field_name in invalid_source_fields:
            statuses[field_name] = "invalid"
            continue
        if source is None:
            statuses[field_name] = "source_missing"
            continue
        current = _interval_value(current_interval, field_name)
        desired = int(round(source))
        member[interval_member_keys[field_name]] = desired
        _set_status(
            field_name,
            source,
            current,
            desired,
            statuses=statuses,
            source_values=source_values,
            current_values=current_values,
            desired_values=desired_values,
        )

    # Zone labels are descriptive only. Reuse exactly the legacy conversions,
    # including their rounding, fixed power cap, and maximum-HR table/mode.
    for field_name, source, threshold, table_key, mapper, dependencies in (
        ("power_zones", sport.power_zones, sport.ftp, "power", map_power_zones,
         {"ftp", "power_zones"}),
        ("hr_zones", sport.hr_zones, sport.max_hr, "heartRate", map_hr_zones,
         {"max_hr", "hr_zones"}),
    ):
        if field_name not in selection.effective:
            continue
        source_values[field_name] = list(source)
        current_values[field_name] = _interval_value(current_interval, field_name)
        if dependencies & set(sport.invalid_fields):
            statuses[field_name] = "invalid"
            continue
        if threshold is None or not source:
            statuses[field_name] = "source_missing"
            continue
        rows = current_interval.get(table_key)
        if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
            statuses[field_name] = "invalid"
            continue
        try:
            interval_body[table_key] = mapper(source, float(int(round(threshold))), rows)
        except (ValueError, TypeError, OverflowError):
            statuses[field_name] = "invalid"
            continue
        desired = _zone_shape(interval_body[table_key])
        if field_name == "hr_zones":
            member["heartRateComputeMode"] = HEART_RATE_COMPUTE_MODE_MAX_HR
            desired = (HEART_RATE_COMPUTE_MODE_MAX_HR, desired)
        desired_values[field_name] = desired
        statuses[field_name] = (
            "unchanged" if current_values[field_name] == desired else "would_update"
        )

    personal_sources = {
        "weight": (
            _one_decimal(athlete.weight) if athlete.weight is not None else None
        ),
        "height": athlete.height_cm,
        "birth_date": athlete.birth_date,
        "sex": athlete.sex,
    }
    personal_updates: dict[str, Any] = {}
    for field_name in selection.effective:
        if field_name not in _PERSONAL_FIELDS:
            continue
        source = personal_sources[field_name]
        if field_name in invalid_source_fields:
            statuses[field_name] = "invalid"
            continue
        if source is None:
            statuses[field_name] = "source_missing"
            continue
        current = _current_personal_value(current_user, field_name)
        personal_updates[field_name] = source
        _set_status(
            field_name,
            source,
            current,
            source,
            statuses=statuses,
            source_values=source_values,
            current_values=current_values,
            desired_values=desired_values,
        )
    personal_payload = (
        build_personal_user_info_payload_updates(current_user, personal_updates)
        if _PERSONAL_FIELDS.intersection(selection.effective)
        else {}
    )

    interval_effective = [
        field_name
        for field_name in selection.effective
        if field_name in _INTERVAL_FIELDS
    ]
    personal_effective = [
        field_name
        for field_name in selection.effective
        if field_name in _PERSONAL_FIELDS
    ]
    if any(statuses.get(name) == "invalid" for name in interval_effective):
        for field_name in interval_effective:
            if statuses.get(field_name) != "source_missing":
                statuses[field_name] = "invalid"
        interval_changed: tuple[str, ...] = ()
    else:
        interval_changed = tuple(
            name for name in interval_effective if statuses.get(name) == "would_update"
        )
    unsafe_missing_weight = (
        current_user.get("weight") is None
        and statuses.get("weight") not in {"would_update", "unchanged"}
    )
    if unsafe_missing_weight or any(
        statuses.get(name) == "invalid" for name in personal_effective
    ):
        for field_name in personal_effective:
            if statuses.get(field_name) != "source_missing":
                statuses[field_name] = "invalid"
        personal_changed: tuple[str, ...] = ()
    else:
        personal_changed = tuple(
            name for name in personal_effective if statuses.get(name) == "would_update"
        )

    return RiderSettingsPlan(
        selection=selection,
        interval_body=interval_body,
        personal_payload=personal_payload,
        field_statuses=statuses,
        interval_changed_fields=interval_changed,
        personal_changed_fields=personal_changed,
        source_values=source_values,
        current_values=current_values,
        desired_values=desired_values,
    )


def _verify_interval_state(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    if actual.get("member") != expected.get("member"):
        return False

    def without_server_ids(value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [
            {key: item for key, item in row.items() if key != "id"}
            if isinstance(row, dict)
            else row
            for row in value
        ]

    table_keys = (
        "power",
        "heartRate",
        "heartRateReserve",
        "heartRateLactateThreshold",
    )
    return all(
        without_server_ids(actual.get(key))
        == without_server_ids(expected.get(key))
        for key in table_keys
    )


def _verify_personal_state(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return build_personal_user_info_payload_updates(actual, {}) == expected


def _rider_result(
    plan: RiderSettingsPlan,
    *,
    updated: int,
    include_values: bool,
) -> RiderSettingsSyncResult:
    statuses = plan.field_statuses
    return RiderSettingsSyncResult(
        requested_fields=plan.selection.requested,
        effective_fields=plan.selection.effective,
        field_statuses=dict(statuses),
        selected=len(plan.selection.effective),
        updated=updated,
        verified=sum(status == "verified" for status in statuses.values()),
        unchanged=sum(status == "unchanged" for status in statuses.values()),
        source_missing=sum(
            status == "source_missing" for status in statuses.values()
        ),
        failed=sum(status in _FAILURE_STATUSES for status in statuses.values()),
        source_values=dict(plan.source_values) if include_values else None,
        current_values=dict(plan.current_values) if include_values else None,
        desired_values=dict(plan.desired_values) if include_values else None,
    )


def sync_rider_settings(
    config: RiderSettingsSyncConfig,
    progress: Progress | None = None,
) -> RiderSettingsSyncResult:
    """Synchronize selected rider settings and verify every written group."""
    if config.sport != "Ride":
        raise SyncError("rider settings sync currently supports Ride only")
    if config.show_values and not config.dry_run:
        raise SyncError("show_values requires dry_run")
    selection = parse_rider_fields(config.fields)
    report = progress or _noop
    session = requests.Session()
    region = resolve_region(config.igp_region)
    report("rider settings: authenticating")
    try:
        auth_headers = login(session, config.igp_user, config.igp_password, region)
    except Exception as exc:
        raise SyncError(str(exc)) from exc
    member_id = member_id_from_token(auth_headers)
    headers = mobile_headers(auth_headers, member_id, region)

    report("rider settings: fetching source and destination")
    try:
        sport = intervals_icu.fetch_sport_settings(
            config.intervals_api_key, config.sport, http=session, strict=True
        )
        athlete = intervals_icu.fetch_athlete_settings(
            config.intervals_api_key, http=session
        )
        current_interval = fetch_personal_interval_info(session, headers, region)
        current_user = fetch_user_info(session, headers, region)
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        raise SyncError(f"could not fetch rider settings: {exc}") from exc

    plan = build_rider_settings_plan(
        sport, athlete, current_interval, current_user, selection
    )
    if config.dry_run:
        report("rider settings: dry-run complete")
        return _rider_result(
            plan,
            updated=0,
            include_values=config.show_values,
        )

    updated = 0
    if plan.interval_changed_fields:
        try:
            update_personal_interval_info(session, headers, plan.interval_body, region)
            updated += len(plan.interval_changed_fields)
        except RuntimeError:
            for field_name in plan.interval_changed_fields:
                plan.field_statuses[field_name] = "write_failed"
            report("rider settings: interval group write failed")
        else:
            try:
                interval_after = fetch_personal_interval_info(
                    session, headers, region
                )
            except RuntimeError:
                for field_name in plan.interval_changed_fields:
                    plan.field_statuses[field_name] = "verify_failed"
                report("rider settings: interval group verification failed")
            else:
                status = (
                    "verified"
                    if _verify_interval_state(interval_after, plan.interval_body)
                    else "verify_failed"
                )
                for field_name in plan.interval_changed_fields:
                    plan.field_statuses[field_name] = status
                report(f"rider settings: interval group {status}")

    if plan.personal_changed_fields:
        try:
            update_personal_user_info(
                session, headers, plan.personal_payload, region
            )
            updated += len(plan.personal_changed_fields)
        except RuntimeError:
            for field_name in plan.personal_changed_fields:
                plan.field_statuses[field_name] = "write_failed"
            report("rider settings: personal group write failed")
        else:
            try:
                user_after = fetch_user_info(session, headers, region)
            except RuntimeError:
                for field_name in plan.personal_changed_fields:
                    plan.field_statuses[field_name] = "verify_failed"
                report("rider settings: personal group verification failed")
            else:
                status = (
                    "verified"
                    if _verify_personal_state(user_after, plan.personal_payload)
                    else "verify_failed"
                )
                for field_name in plan.personal_changed_fields:
                    plan.field_statuses[field_name] = status
                report(f"rider settings: personal group {status}")

    return _rider_result(plan, updated=updated, include_values=False)


_THRESHOLD_LABELS = {"ftp": "FTP", "lthr": "LTHR", "mhr": "max HR", "weight": "Weight"}


def _whole_kg(value: Any) -> int | None:
    """Round kg to a whole number; iGPSPORT only accepts integer kilograms."""
    if value is None:
        return None
    try:
        kg = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    if kg <= 0:
        return None
    return kg


def _threshold_values(
    member: dict[str, Any],
    *,
    weight: float | None = None,
) -> dict[str, int | None]:
    def _int_val(key: str) -> int | None:
        value = member.get(key)
        if value is None:
            return None
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None

    return {
        "ftp": _int_val("ftp"),
        "lthr": _int_val("lthr"),
        "mhr": _int_val("mhr"),
        # App profile weight comes from User/UserInfo, not UserIntervalInfo.member.
        "weight": _whole_kg(weight),
    }


def _threshold_fingerprint(
    settings: SportSettings,
    weight: float | None = None,
) -> str:
    ftp = int(round(settings.ftp or 0))
    mhr = int(round(settings.max_hr or 0))
    lthr = int(round(settings.lthr)) if settings.lthr is not None else ""
    weight_part = _whole_kg(weight) if weight is not None else ""
    return f"{ftp}|{lthr}|{mhr}|{weight_part}"


def _intervals_threshold_values(
    settings: SportSettings,
    weight: float | None = None,
) -> dict[str, int | None]:
    return {
        "ftp": int(round(settings.ftp or 0)),
        "lthr": int(round(settings.lthr)) if settings.lthr is not None else None,
        "mhr": int(round(settings.max_hr or 0)),
        "weight": _whole_kg(weight),
    }


def compare_profile_thresholds(
    current: dict[str, Any],
    settings: SportSettings,
    *,
    weight: float | None = None,
    current_weight: float | None = None,
) -> ProfileThresholdStatus:
    """Return whether FTP, LTHR, max HR, or weight would change on sync."""
    desired = apply_intervals_settings(current, settings)
    member = current.get("member")
    desired_member = desired.get("member")
    current_vals = _threshold_values(
        member if isinstance(member, dict) else {},
        weight=current_weight,
    )
    desired_vals = _threshold_values(
        desired_member if isinstance(desired_member, dict) else {},
        weight=weight,
    )

    keys_to_compare = ["ftp", "mhr"]
    if settings.lthr is not None:
        keys_to_compare.append("lthr")
    if weight is not None and _whole_kg(weight) is not None:
        keys_to_compare.append("weight")

    differences: list[str] = []
    for key in keys_to_compare:
        if current_vals.get(key) != desired_vals.get(key):
            label = _THRESHOLD_LABELS[key]
            differences.append(
                f"{label}: iGPSPORT {current_vals.get(key)} "
                f"→ intervals.icu {desired_vals.get(key)}"
            )

    return ProfileThresholdStatus(
        needs_sync=bool(differences),
        differences=differences,
        intervals_fingerprint=_threshold_fingerprint(settings, weight),
        intervals=_intervals_threshold_values(settings, weight),
        igpsport=current_vals,
    )


def _validate_sport_settings(settings: SportSettings) -> None:
    if settings.ftp is None or settings.ftp <= 0:
        raise SyncError("intervals.icu sport settings missing FTP")
    if settings.max_hr is None or settings.max_hr <= 0:
        raise SyncError("intervals.icu sport settings missing max HR")
    if not settings.power_zones:
        raise SyncError("intervals.icu sport settings missing power zones")
    if not settings.hr_zones:
        raise SyncError("intervals.icu sport settings missing HR zones")


def apply_intervals_settings(
    body: dict[str, Any],
    settings: SportSettings,
) -> dict[str, Any]:
    """Return a copy of the iGPSPORT payload with thresholds and zones updated.

    Weight is updated separately via User/UpdatePersonalUserInfo — UpdatePersonalIntervalInfo
    ignores member.weight.
    """
    updated = copy.deepcopy(body)
    member = updated.get("member")
    if not isinstance(member, dict):
        raise SyncError("iGPSPORT profile payload has no member block")

    ftp = int(round(settings.ftp or 0))
    max_hr = int(round(settings.max_hr or 0))
    lthr = int(round(settings.lthr or 0)) if settings.lthr is not None else member.get("lthr")

    member["ftp"] = ftp
    member["mhr"] = max_hr
    if lthr is not None:
        member["lthr"] = lthr
    member["heartRateComputeMode"] = HEART_RATE_COMPUTE_MODE_MAX_HR

    power = updated.get("power")
    if isinstance(power, list) and power:
        updated["power"] = map_power_zones(settings.power_zones, float(ftp), power)

    heart_rate = updated.get("heartRate")
    if isinstance(heart_rate, list) and heart_rate:
        updated["heartRate"] = map_hr_zones(settings.hr_zones, float(max_hr), heart_rate)

    return updated


def _report_summary(
    report: Progress,
    label: str,
    body: dict[str, Any],
    *,
    weight: float | None = None,
) -> None:
    member = body.get("member") if isinstance(body.get("member"), dict) else {}
    power = body.get("power") if isinstance(body.get("power"), list) else []
    heart_rate = body.get("heartRate") if isinstance(body.get("heartRate"), list) else []
    report(f"{label}:")
    parts = [
        f"{key}={member[key]}"
        for key in ("ftp", "mhr", "lthr", "heartRateComputeMode", "quietHeartRate")
        if key in member
    ]
    if weight is not None:
        parts.append(f"weight={weight}")
    report("  member: " + ", ".join(parts))
    report(f"  power:  {zone_range_summary(power)}")
    report(f"  heartRate: {zone_range_summary(heart_rate)}")


def sync_profile_zones(
    config: ProfileSyncConfig,
    progress: Progress | None = None,
) -> ProfileSyncResult:
    """Fetch intervals.icu sport settings and push them to iGPSPORT."""
    report = progress or _noop

    session = requests.Session()
    region = resolve_region(config.igp_region)
    report("Logging in to iGPSPORT…")
    try:
        auth_headers = login(session, config.igp_user, config.igp_password, region)
    except Exception as exc:
        raise SyncError(str(exc)) from exc

    member_id = member_id_from_token(auth_headers)
    headers = mobile_headers(auth_headers, member_id, region)

    report("Fetching sport settings from intervals.icu…")
    try:
        settings = intervals_icu.fetch_sport_settings(
            config.intervals_api_key,
            config.sport,
            http=session,
        )
    except requests.RequestException as exc:
        raise SyncError(f"Could not fetch intervals.icu sport settings: {exc}") from exc

    _validate_sport_settings(settings)

    report("Fetching athlete weight from intervals.icu…")
    try:
        weight = intervals_icu.fetch_athlete_weight(
            config.intervals_api_key,
            http=session,
        )
    except requests.RequestException as exc:
        raise SyncError(f"Could not fetch intervals.icu athlete weight: {exc}") from exc

    report("Fetching iGPSPORT profile…")
    try:
        current = fetch_personal_interval_info(session, headers, region)
        user_info = fetch_user_info(session, headers, region)
    except RuntimeError as exc:
        raise SyncError(str(exc)) from exc

    weight_before = user_info.get("weight")
    target_weight = _whole_kg(weight)

    updated = apply_intervals_settings(current, settings)
    _report_summary(report, "Before", current, weight=weight_before)
    _report_summary(
        report,
        "After",
        updated,
        weight=float(target_weight) if target_weight is not None else weight_before,
    )

    report("Updating iGPSPORT profile…")
    try:
        update_personal_interval_info(session, headers, updated, region)
    except RuntimeError as exc:
        raise SyncError(str(exc)) from exc

    if target_weight is not None and _whole_kg(weight_before) != target_weight:
        saved_city_id = user_info.get("cityId")
        report("Updating iGPSPORT weight…")
        try:
            update_user_weight(session, headers, target_weight, region)
        except RuntimeError as exc:
            raise SyncError(str(exc)) from exc
        user_info_after_weight = fetch_user_info(session, headers, region)
        city_after = user_info_after_weight.get("cityId")
        if saved_city_id not in (None, 0, "0") and city_after in (None, 0, "", "0"):
            report(
                "Note: iGPSPORT cleared profile location while updating weight; "
                "set location again in the app."
            )

    report("Verifying iGPSPORT profile…")
    try:
        after = fetch_personal_interval_info(session, headers, region)
        user_info_after = fetch_user_info(session, headers, region)
    except RuntimeError as exc:
        raise SyncError(str(exc)) from exc

    weight_after = user_info_after.get("weight")

    _report_summary(report, "Read-back", after, weight=weight_after)
    return ProfileSyncResult(
        before=current,
        after=after,
        weight_before=float(weight_before) if weight_before is not None else None,
        weight_after=float(weight_after) if weight_after is not None else None,
    )


def fetch_profile_threshold_status(config: ProfileSyncConfig) -> ProfileThresholdStatus:
    """Compare iGPSPORT profile thresholds with intervals.icu sport settings."""
    session = requests.Session()
    region = resolve_region(config.igp_region)
    try:
        auth_headers = login(session, config.igp_user, config.igp_password, region)
    except Exception as exc:
        raise SyncError(str(exc)) from exc

    member_id = member_id_from_token(auth_headers)
    headers = mobile_headers(auth_headers, member_id, region)

    try:
        settings = intervals_icu.fetch_sport_settings(
            config.intervals_api_key,
            config.sport,
            http=session,
        )
    except requests.RequestException as exc:
        raise SyncError(f"Could not fetch intervals.icu sport settings: {exc}") from exc

    _validate_sport_settings(settings)

    try:
        weight = intervals_icu.fetch_athlete_weight(
            config.intervals_api_key,
            http=session,
        )
    except requests.RequestException as exc:
        raise SyncError(f"Could not fetch intervals.icu athlete weight: {exc}") from exc

    try:
        current = fetch_personal_interval_info(session, headers, region)
        user_info = fetch_user_info(session, headers, region)
    except RuntimeError as exc:
        raise SyncError(str(exc)) from exc

    return compare_profile_thresholds(
        current,
        settings,
        weight=weight,
        current_weight=user_info.get("weight"),
    )


def result_payload(result: ProfileSyncResult, *, ok: bool, error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "source": "igpsport",
    }
    if result.before is not None:
        payload["before"] = profile_summary(result.before, weight=result.weight_before)
    if result.after is not None:
        summary = profile_summary(result.after, weight=result.weight_after)
        payload.update(summary)
        payload["after"] = summary
    if error is not None:
        payload["error"] = error
    return payload
