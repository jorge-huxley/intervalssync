"""Dropbox OAuth and upload helpers."""

from __future__ import annotations

import os
from pathlib import Path

import dropbox
from dropbox import DropboxOAuth2FlowNoRedirect
from dropbox.files import WriteMode

from ._dropbox_app_key import DROPBOX_APP_KEY as BUILD_DROPBOX_APP_KEY

DROPBOX_APP_KEY_ENV = "IGPSYNC_DROPBOX_APP_KEY"
DEFAULT_DROPBOX_FOLDER = "/igpsport-fit"


def get_dropbox_app_key() -> str | None:
    """Return the Dropbox app key from env or the build-stamped constant."""
    return os.getenv(DROPBOX_APP_KEY_ENV) or BUILD_DROPBOX_APP_KEY or None


def dropbox_path_for(folder: str, ride_id: int) -> str:
    """Return the Dropbox app-folder path for an iGPSPORT ride."""
    clean_folder = (folder or DEFAULT_DROPBOX_FOLDER).strip()
    if not clean_folder.startswith("/"):
        clean_folder = f"/{clean_folder}"
    clean_folder = clean_folder.rstrip("/")
    return f"{clean_folder}/igpsport_{ride_id}.fit"


def start_dropbox_auth(app_key: str) -> tuple[DropboxOAuth2FlowNoRedirect, str]:
    """Start a PKCE OAuth flow and return the flow object plus auth URL."""
    auth_flow = DropboxOAuth2FlowNoRedirect(
        app_key,
        use_pkce=True,
        token_access_type="offline",
        scope=["account_info.read", "files.content.write"],
    )
    return auth_flow, auth_flow.start()


def finish_dropbox_auth(
    auth_flow: DropboxOAuth2FlowNoRedirect, auth_code: str
) -> str | None:
    """Finish OAuth and return the long-lived refresh token."""
    result = auth_flow.finish(auth_code.strip())
    return result.refresh_token


def upload_to_dropbox(
    fit_path: Path,
    ride_id: int,
    refresh_token: str,
    app_key: str,
    folder: str = DEFAULT_DROPBOX_FOLDER,
) -> bool:
    """Upload a FIT file to Dropbox, overwriting the ride's existing file."""
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
    return True
