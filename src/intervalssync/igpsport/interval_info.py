"""iGPSPORT mobile API for personal interval / zone profile."""

from __future__ import annotations

import base64
import json
from typing import Any

import requests

IGPS_MOBILE_API = "https://prod.en.igpsport.com/service/mobile/api"
GET_INTERVAL_URL = f"{IGPS_MOBILE_API}/v2/User/UserIntervalInfo"
UPDATE_INTERVAL_URL = f"{IGPS_MOBILE_API}/User/UpdatePersonalIntervalInfo"

# iGPSPORT heartRateComputeMode: 0 = max HR, 1 = HRR, 2 = LTHR.
HEART_RATE_COMPUTE_MODE_MAX_HR = 0


def member_id_from_token(auth_headers: dict[str, str]) -> int | None:
    token = auth_headers.get("Authorization", "").removeprefix("Bearer ").strip()
    parts = token.split(".")
    if len(parts) < 2:
        return None
    segment = parts[1]
    padding = "=" * (-len(segment) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(segment + padding))
    except (ValueError, json.JSONDecodeError):
        return None
    for key in ("memberid", "memberId", "sub"):
        value = payload.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


def mobile_headers(auth_headers: dict[str, str], member_id: int | None) -> dict[str, str]:
    headers = {
        **auth_headers,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "Accept-Language": "en",
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": "intervalssync/1.0",
        "qiwu-app-version": "8.06.36",
        "timezone": "UTC",
    }
    if member_id is not None:
        headers["qiwu-uid"] = str(member_id)
    return headers


def _unwrap_api_data(response_json: Any) -> dict[str, Any] | None:
    if not isinstance(response_json, dict):
        return None
    if response_json.get("code") != 0:
        return None
    data = response_json.get("data")
    if isinstance(data, dict) and "member" in data:
        return data
    if isinstance(data, dict):
        nested = data.get("data")
        if isinstance(nested, dict) and "member" in nested:
            return nested
        for key in ("intervalInfo", "userIntervalInfo", "personalIntervalInfo"):
            nested = data.get(key)
            if isinstance(nested, dict) and "member" in nested:
                return nested
    if "member" in response_json:
        return response_json
    return None


def fetch_personal_interval_info(
    session: requests.Session,
    headers: dict[str, str],
) -> dict[str, Any]:
    """GET v2/User/UserIntervalInfo."""
    get_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
    try:
        resp = session.get(GET_INTERVAL_URL, headers=get_headers, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(f"GET UserIntervalInfo failed: {exc}") from exc

    try:
        body = resp.json()
    except ValueError as exc:
        raise RuntimeError(
            f"GET UserIntervalInfo: HTTP {resp.status_code}, non-JSON body"
        ) from exc

    payload = _unwrap_api_data(body)
    if payload is None:
        raise RuntimeError(
            f"GET UserIntervalInfo: HTTP {resp.status_code}, "
            f"code={body.get('code') if isinstance(body, dict) else '?'}, "
            f"no member block in response"
        )
    return payload


def update_personal_interval_info(
    session: requests.Session,
    headers: dict[str, str],
    body: dict[str, Any],
) -> dict[str, Any]:
    """POST UpdatePersonalIntervalInfo."""
    try:
        resp = session.post(UPDATE_INTERVAL_URL, headers=headers, json=body, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(f"POST UpdatePersonalIntervalInfo failed: {exc}") from exc

    try:
        result = resp.json()
    except ValueError as exc:
        raise RuntimeError(
            f"POST UpdatePersonalIntervalInfo: HTTP {resp.status_code}, non-JSON body"
        ) from exc

    if not resp.ok:
        raise RuntimeError(f"POST UpdatePersonalIntervalInfo: HTTP {resp.status_code}")

    if isinstance(result, dict) and result.get("code") not in (0, None):
        message = result.get("message") or "unknown error"
        raise RuntimeError(f"POST UpdatePersonalIntervalInfo failed: {message}")

    return result if isinstance(result, dict) else {}


def zone_range_summary(zones: list[dict[str, Any]]) -> str:
    if not zones:
        return "(none)"
    return " | ".join(f"{z.get('start')}-{z.get('end')}" for z in zones)


def profile_summary(body: dict[str, Any]) -> dict[str, Any]:
    """Return a compact summary dict for CLI JSON output."""
    member = body.get("member") if isinstance(body.get("member"), dict) else {}
    power = body.get("power") if isinstance(body.get("power"), list) else []
    heart_rate = body.get("heartRate") if isinstance(body.get("heartRate"), list) else []
    return {
        "ftp": member.get("ftp"),
        "lthr": member.get("lthr"),
        "mhr": member.get("mhr"),
        "heart_rate_compute_mode": member.get("heartRateComputeMode"),
        "power_zones": zone_range_summary(power),
        "hr_zones": zone_range_summary(heart_rate),
    }
