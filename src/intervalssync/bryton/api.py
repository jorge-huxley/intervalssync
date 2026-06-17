"""REST FIT download for Bryton Active (Android app API)."""
from __future__ import annotations

from pathlib import Path

import requests

from .ddp import DEFAULT_HOST, BrytonSession

DEFAULT_API_KEY = "UHIJdntFZFkZaVJsInRHfRcYES08Fwp0Bwkf"


def download_fit_bytes(
    activity_id: str,
    session: BrytonSession,
    *,
    api_key: str = DEFAULT_API_KEY,
) -> bytes:
    """Download ride FIT bytes for activity_id."""
    url = f"https://{session.host}/api/activity"
    headers = {
        "X-User-Id": session.user_id,
        "X-Auth-Token": session.auth_token,
        "x-api-key": api_key,
        "User-Agent": "okhttp/4.12.0",
        "Accept-Encoding": "gzip",
    }
    resp = requests.get(url, params={"id": activity_id}, headers=headers, timeout=120)
    resp.raise_for_status()
    data = resp.content
    if len(data) < 14 or b".FIT" not in data[8:14]:
        raise ValueError(
            f"Response does not look like FIT ({len(data)} bytes, head={data[:16]!r})"
        )
    return data


def download_fit_to_path(
    activity_id: str,
    session: BrytonSession,
    dest_path: Path,
    *,
    api_key: str = DEFAULT_API_KEY,
) -> Path:
    """Download FIT file to dest_path."""
    data = download_fit_bytes(activity_id, session, api_key=api_key)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(data)
    return dest_path
