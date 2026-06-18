"""Check GitHub Releases for a newer version of the app.

Pure logic, no UI. Fails silently (returns None) on any problem — offline, rate
limited, parse errors — so it never disrupts launch.
"""

from __future__ import annotations

import requests
from packaging.version import InvalidVersion, Version

REPO = "jorge-huxley/intervalssync"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"


def check_for_update(
    current: str, timeout: float = 5.0, allow_dev: bool = False
) -> str | None:
    """Return the latest release version (e.g. "0.2.3") if it is newer than
    `current`, otherwise None. Returns None on any error.

    Dev/local builds (e.g. "0.0.0+dev") are skipped for the automatic check, but
    `allow_dev=True` includes them — useful for a manual "Check for updates" so
    the flow is testable without a tagged build.
    """
    try:
        current_version = Version(current)
    except InvalidVersion:
        return None

    if not allow_dev and (current_version.local or current_version.is_devrelease):
        return None

    try:
        resp = requests.get(
            LATEST_RELEASE_API,
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        resp.raise_for_status()
        tag = resp.json().get("tag_name")
    except (requests.RequestException, ValueError):
        return None

    if not tag:
        return None

    latest = tag.lstrip("v")
    try:
        if Version(latest) > current_version:
            return latest
    except InvalidVersion:
        return None
    return None
