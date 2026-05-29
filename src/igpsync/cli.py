"""Headless CLI — preserves the original `main.py` behavior.

Reads non-secret settings from config.json (with .env fallback) and secrets
from the OS vault, falling back to .env for backward compatibility.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from . import config as config_module
from . import secrets as secrets_module
from .core import SyncConfig, SyncError, sync


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def build_sync_config() -> SyncConfig:
    load_dotenv()
    cfg = config_module.load()
    store = secrets_module.KeyringSecretStore()

    igp_user = cfg.igp_user or os.environ.get("IGP_USER", "")
    igp_password = store.get(secrets_module.IGP_PASSWORD) or os.environ.get("IGP_PASS", "")
    api_key = store.get(secrets_module.INTERVALS_API_KEY) or os.getenv("INTERVALS_API_KEY")

    if not igp_user or not igp_password:
        raise SyncError(
            "Missing iGPSPORT credentials. Run the GUI to save them, or set "
            "IGP_USER / IGP_PASS in .env."
        )

    return SyncConfig(
        igp_user=igp_user,
        igp_password=igp_password,
        intervals_api_key=api_key,
        max_activities=int(os.getenv("MAX_ACTIVITIES", str(cfg.max_activities))),
        download_dir=cfg.download_dir,
        delete_after_upload=_env_bool("DELETE_AFTER_UPLOAD", cfg.delete_after_upload),
        force_resync=_env_bool("FORCE_RESYNC", cfg.force_resync),
        list_activities=_env_bool("STEP_LIST_ACTIVITIES", cfg.step_list_activities),
        get_download_url=_env_bool("STEP_GET_DOWNLOAD_URL", cfg.step_get_download_url),
        download_fit=_env_bool("STEP_DOWNLOAD_FIT", cfg.step_download_fit),
        upload_intervals=_env_bool("STEP_UPLOAD_INTERVALS", cfg.step_upload_intervals),
    )


def _force_utf8_console() -> None:
    """Avoid UnicodeEncodeError when printing symbols on a cp1252 console."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main() -> int:
    _force_utf8_console()
    try:
        sync_config = build_sync_config()
        result = sync(sync_config, progress=print)
    except SyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"\nDone. listed={result.listed} uploaded={result.uploaded} "
        f"skipped={result.skipped} downloaded={result.downloaded} "
        f"failed={result.failed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
