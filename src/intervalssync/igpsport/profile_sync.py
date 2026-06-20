"""Sync thresholds and zones from intervals.icu to iGPSPORT profile."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

import requests

from .. import intervals_icu
from ..intervals_icu import SportSettings
from .core import SyncError, login
from .interval_info import (
    HEART_RATE_COMPUTE_MODE_MAX_HR,
    fetch_personal_interval_info,
    mobile_headers,
    member_id_from_token,
    profile_summary,
    update_personal_interval_info,
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
    sport: str = "Ride"


@dataclass
class ProfileSyncResult:
    before: dict[str, Any] | None
    after: dict[str, Any] | None


@dataclass
class ProfileThresholdStatus:
    needs_sync: bool
    differences: list[str]
    intervals_fingerprint: str
    intervals: dict[str, int | None]
    igpsport: dict[str, int | None]


_THRESHOLD_LABELS = {"ftp": "FTP", "lthr": "LTHR", "mhr": "max HR"}


def _threshold_values(member: dict[str, Any]) -> dict[str, int | None]:
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
    }


def _threshold_fingerprint(settings: SportSettings) -> str:
    ftp = int(round(settings.ftp or 0))
    mhr = int(round(settings.max_hr or 0))
    lthr = int(round(settings.lthr)) if settings.lthr is not None else ""
    return f"{ftp}|{lthr}|{mhr}"


def _intervals_threshold_values(settings: SportSettings) -> dict[str, int | None]:
    return {
        "ftp": int(round(settings.ftp or 0)),
        "lthr": int(round(settings.lthr)) if settings.lthr is not None else None,
        "mhr": int(round(settings.max_hr or 0)),
    }


def compare_profile_thresholds(
    current: dict[str, Any],
    settings: SportSettings,
) -> ProfileThresholdStatus:
    """Return whether FTP, LTHR, or max HR would change on sync."""
    desired = apply_intervals_settings(current, settings)
    member = current.get("member")
    desired_member = desired.get("member")
    current_vals = _threshold_values(member if isinstance(member, dict) else {})
    desired_vals = _threshold_values(desired_member if isinstance(desired_member, dict) else {})

    keys_to_compare = ["ftp", "mhr"]
    if settings.lthr is not None:
        keys_to_compare.append("lthr")

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
        intervals_fingerprint=_threshold_fingerprint(settings),
        intervals=_intervals_threshold_values(settings),
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
    """Return a copy of the iGPSPORT payload with thresholds and zones updated."""
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


def _report_summary(report: Progress, label: str, body: dict[str, Any]) -> None:
    member = body.get("member") if isinstance(body.get("member"), dict) else {}
    power = body.get("power") if isinstance(body.get("power"), list) else []
    heart_rate = body.get("heartRate") if isinstance(body.get("heartRate"), list) else []
    report(f"{label}:")
    report(
        "  member: "
        + ", ".join(
            f"{key}={member[key]}"
            for key in ("ftp", "mhr", "lthr", "heartRateComputeMode", "quietHeartRate")
            if key in member
        )
    )
    report(f"  power:  {zone_range_summary(power)}")
    report(f"  heartRate: {zone_range_summary(heart_rate)}")


def sync_profile_zones(
    config: ProfileSyncConfig,
    progress: Progress | None = None,
) -> ProfileSyncResult:
    """Fetch intervals.icu sport settings and push them to iGPSPORT."""
    report = progress or _noop

    session = requests.Session()
    report("Logging in to iGPSPORT…")
    try:
        auth_headers = login(session, config.igp_user, config.igp_password)
    except Exception as exc:
        raise SyncError(str(exc)) from exc

    member_id = member_id_from_token(auth_headers)
    headers = mobile_headers(auth_headers, member_id)

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

    report("Fetching iGPSPORT profile…")
    try:
        current = fetch_personal_interval_info(session, headers)
    except RuntimeError as exc:
        raise SyncError(str(exc)) from exc

    updated = apply_intervals_settings(current, settings)
    _report_summary(report, "Before", current)
    _report_summary(report, "After", updated)

    report("Updating iGPSPORT profile…")
    try:
        update_personal_interval_info(session, headers, updated)
    except RuntimeError as exc:
        raise SyncError(str(exc)) from exc

    report("Verifying iGPSPORT profile…")
    try:
        after = fetch_personal_interval_info(session, headers)
    except RuntimeError as exc:
        raise SyncError(str(exc)) from exc

    _report_summary(report, "Read-back", after)
    return ProfileSyncResult(before=current, after=after)


def fetch_profile_threshold_status(config: ProfileSyncConfig) -> ProfileThresholdStatus:
    """Compare iGPSPORT profile thresholds with intervals.icu sport settings."""
    session = requests.Session()
    try:
        auth_headers = login(session, config.igp_user, config.igp_password)
    except Exception as exc:
        raise SyncError(str(exc)) from exc

    member_id = member_id_from_token(auth_headers)
    headers = mobile_headers(auth_headers, member_id)

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
        current = fetch_personal_interval_info(session, headers)
    except RuntimeError as exc:
        raise SyncError(str(exc)) from exc

    return compare_profile_thresholds(current, settings)


def result_payload(result: ProfileSyncResult, *, ok: bool, error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "source": "igpsport",
    }
    if result.before is not None:
        payload["before"] = profile_summary(result.before)
    if result.after is not None:
        summary = profile_summary(result.after)
        payload.update(summary)
        payload["after"] = summary
    if error is not None:
        payload["error"] = error
    return payload
