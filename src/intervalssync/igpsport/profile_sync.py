"""Sync thresholds, zones, and weight from intervals.icu to iGPSPORT profile."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

import requests

from .. import intervals_icu
from ..intervals_icu import SportSettings
from .core import SyncError, login
from .region import resolve_region
from .interval_info import (
    HEART_RATE_COMPUTE_MODE_MAX_HR,
    fetch_personal_interval_info,
    fetch_user_info,
    mobile_headers,
    member_id_from_token,
    profile_summary,
    update_personal_interval_info,
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

    Weight is updated separately via User/UpdateUserInfo — UpdatePersonalIntervalInfo
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
                "set location again in the app. Later syncs keep it if weight is unchanged."
            )

    report("Verifying iGPSPORT profile…")
    try:
        after = fetch_personal_interval_info(session, headers)
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
