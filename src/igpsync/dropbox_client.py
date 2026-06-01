"""Dropbox OAuth and upload helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect
from dropbox.exceptions import ApiError
from dropbox.files import FileMetadata, WriteMode
from requests.exceptions import HTTPError

from ._dropbox_app_key import DROPBOX_APP_KEY as BUILD_DROPBOX_APP_KEY

DROPBOX_APP_KEY_ENV = "IGPSYNC_DROPBOX_APP_KEY"
DEFAULT_DROPBOX_FOLDER = "/igpsport-fit"

# Matches the FIT file names we write, e.g. "igpsport_12345.fit".
_FIT_NAME_RE = re.compile(r"^igpsport_(\d+)\.fit$")


def get_dropbox_app_key() -> str | None:
    """Return the Dropbox app key from env or the build-stamped constant."""
    return os.getenv(DROPBOX_APP_KEY_ENV) or BUILD_DROPBOX_APP_KEY or None


def normalize_folder(folder: str) -> str:
    """Return a leading-slash, no-trailing-slash Dropbox folder path."""
    clean = (folder or DEFAULT_DROPBOX_FOLDER).strip()
    if not clean.startswith("/"):
        clean = f"/{clean}"
    return clean.rstrip("/")


def dropbox_path_for(folder: str, ride_id: int) -> str:
    """Return the Dropbox app-folder path for an iGPSPORT ride."""
    return f"{normalize_folder(folder)}/igpsport_{ride_id}.fit"


def start_dropbox_auth(app_key: str) -> tuple[DropboxOAuth2FlowNoRedirect, str]:
    """Start a PKCE OAuth flow and return the flow object plus auth URL."""
    auth_flow = DropboxOAuth2FlowNoRedirect(
        app_key,
        use_pkce=True,
        token_access_type="offline",
        # files.metadata.read lets us list the folder to skip rides already there.
        scope=[
            "account_info.read",
            "files.metadata.read",
            "files.content.write",
        ],
    )
    return auth_flow, auth_flow.start()


def _friendly_auth_error(exc: HTTPError) -> str:
    """Turn a token-exchange HTTPError into a user-facing message.

    The Dropbox SDK calls ``raise_for_status()`` and drops the response body,
    so a failed exchange surfaces only a generic "400 Client Error". The most
    common failure with the copy-paste flow is an expired/used code
    (``invalid_grant``) — give that a friendly hint and fall back to Dropbox's
    raw error text for anything unexpected.
    """
    body = ""
    if exc.response is not None:
        body = exc.response.text.strip()
    if "invalid_grant" in body:
        return (
            "That authorization code expired or was already used. Tap "
            "Connect Dropbox again and paste the new code quickly."
        )
    return f"{exc} — {body}" if body else str(exc)


def finish_dropbox_auth(
    auth_flow: DropboxOAuth2FlowNoRedirect, auth_code: str
) -> str | None:
    """Finish OAuth and return the long-lived refresh token."""
    try:
        result = auth_flow.finish(auth_code.strip())
    except HTTPError as exc:
        raise RuntimeError(_friendly_auth_error(exc)) from exc
    return result.refresh_token


def upload_to_dropbox(
    fit_path: Path,
    ride_id: int,
    refresh_token: str,
    app_key: str,
    folder: str = DEFAULT_DROPBOX_FOLDER,
) -> None:
    """Upload a FIT file to Dropbox, overwriting the ride's existing file.

    Raises on failure; a normal return means the upload succeeded.
    """
    target = dropbox_path_for(folder, ride_id)
    with dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
        timeout=100,
        user_agent="igpsport-intervals",
    ) as dbx:
        with fit_path.open("rb") as f:
            dbx.files_upload(
                f.read(),
                target,
                mode=WriteMode.overwrite,
                mute=True,
            )


def list_dropbox_ride_ids(
    folder: str, refresh_token: str, app_key: str
) -> set[int]:
    """Return iGPSPORT ride ids that already have a FIT file in the folder.

    Returns an empty set when the folder doesn't exist yet. Raises on other
    Dropbox errors so the caller can decide whether to treat them as fatal.
    """
    base = normalize_folder(folder)
    ride_ids: set[int] = set()
    with dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
        timeout=100,
        user_agent="igpsport-intervals",
    ) as dbx:
        try:
            result = dbx.files_list_folder(base)
        except ApiError as exc:
            if exc.error.is_path() and exc.error.get_path().is_not_found():
                return ride_ids
            raise
        entries = list(result.entries)
        while result.has_more:
            result = dbx.files_list_folder_continue(result.cursor)
            entries.extend(result.entries)

    for entry in entries:
        if not isinstance(entry, FileMetadata):
            continue
        match = _FIT_NAME_RE.match(entry.name)
        if match:
            ride_ids.add(int(match.group(1)))
    return ride_ids
