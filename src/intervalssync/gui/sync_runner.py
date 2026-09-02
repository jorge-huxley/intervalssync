"""Shared activity-sync helpers for the GUI (manual Sync + auto-sync)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..bryton.core import SyncConfig as BrytonSyncConfig, sync as bryton_sync
from ..bryton.exceptions import BrytonSyncError
from ..dropbox_client import get_dropbox_app_key
from ..igpsport.core import SyncConfig as IgpSyncConfig, SyncError, sync as igpsport_sync
from . import config as config_module
from . import secrets as secrets_module

Progress = Callable[[str], None]

_sync_lock = threading.Lock()


@dataclass
class ActivitySyncOutcome:
    uploaded: int = 0
    uploaded_dropbox: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    # True when another sync held the lock (manual or auto).
    busy: bool = False


def try_begin_sync() -> bool:
    """Acquire the global sync lock without blocking."""
    return _sync_lock.acquire(blocking=False)


def end_sync() -> None:
    """Release the global sync lock."""
    _sync_lock.release()


def igp_sync_config(
    config: config_module.AppConfig,
    *,
    igp_password: str,
    api_key: str | None,
    dropbox_refresh_token: str | None,
    dropbox_app_key: str | None,
) -> IgpSyncConfig:
    return IgpSyncConfig(
        igp_user=config.igp_user,
        igp_password=igp_password,
        igp_region=config.igp_region,
        intervals_api_key=api_key,
        dropbox_refresh_token=dropbox_refresh_token,
        dropbox_app_key=dropbox_app_key,
        max_activities=config.max_activities,
        download_dir=config.download_dir,
        delete_after_upload=config.delete_after_upload,
        force_resync=config.force_resync,
        activity_type=config.activity_type,
        list_activities=config.step_list_activities,
        get_download_url=config.step_get_download_url,
        download_fit=config.step_download_fit,
        upload_intervals=config.step_upload_intervals,
        upload_dropbox=config.upload_dropbox,
        dropbox_folder=config.dropbox_folder,
        dropbox_date_filenames=config.dropbox_date_filenames,
    )


def bryton_sync_config(
    config: config_module.AppConfig,
    *,
    bryton_password: str,
    api_key: str | None,
    dropbox_refresh_token: str | None,
    dropbox_app_key: str | None,
) -> BrytonSyncConfig:
    return BrytonSyncConfig(
        bryton_email=config.bryton_user,
        bryton_password=bryton_password,
        intervals_api_key=api_key,
        dropbox_refresh_token=dropbox_refresh_token,
        dropbox_app_key=dropbox_app_key,
        max_activities=config.max_activities,
        download_dir=Path(config.download_dir),
        delete_after_upload=config.delete_after_upload,
        force_resync=config.force_resync,
        activity_type=config.activity_type,
        list_activities=config.step_list_activities,
        download_fit=config.step_download_fit,
        upload_intervals=config.step_upload_intervals,
        upload_dropbox=config.upload_dropbox,
        dropbox_folder=config.dropbox_folder,
        dropbox_date_filenames=config.dropbox_date_filenames,
    )


def run_enabled_activity_sync(
    config: config_module.AppConfig,
    *,
    igp_password: str | None,
    bryton_password: str | None,
    api_key: str | None,
    dropbox_refresh_token: str | None,
    dropbox_app_key: str | None = None,
    progress: Progress | None = None,
) -> ActivitySyncOutcome:
    """Sync all enabled sources. Skips if another sync is already running."""
    if not try_begin_sync():
        return ActivitySyncOutcome(busy=True)

    report = progress or (lambda _msg: None)
    outcome = ActivitySyncOutcome()
    app_key = dropbox_app_key if dropbox_app_key is not None else get_dropbox_app_key()

    try:
        if config.enable_igpsport:
            if not config.igp_user or not igp_password:
                outcome.errors.append("iGPSPORT credentials missing")
            else:
                report("Auto-sync: iGPSPORT…")
                try:
                    result = igpsport_sync(
                        igp_sync_config(
                            config,
                            igp_password=igp_password,
                            api_key=api_key,
                            dropbox_refresh_token=dropbox_refresh_token,
                            dropbox_app_key=app_key,
                        ),
                        progress=report,
                    )
                    outcome.uploaded += result.uploaded
                    outcome.uploaded_dropbox += result.uploaded_dropbox
                    outcome.skipped += result.skipped
                    outcome.failed += result.failed
                except SyncError as exc:
                    outcome.errors.append(str(exc))
                    report(f"✗ iGPSPORT: {exc}")
                except Exception as exc:  # noqa: BLE001 — surface unexpected failures
                    outcome.errors.append(str(exc))
                    report(f"✗ iGPSPORT unexpected error: {exc}")

        if config.enable_bryton:
            if not config.bryton_user or not bryton_password:
                outcome.errors.append("Bryton credentials missing")
            else:
                report("Auto-sync: Bryton…")
                try:
                    result = bryton_sync(
                        bryton_sync_config(
                            config,
                            bryton_password=bryton_password,
                            api_key=api_key,
                            dropbox_refresh_token=dropbox_refresh_token,
                            dropbox_app_key=app_key,
                        ),
                        progress=report,
                    )
                    outcome.uploaded += result.uploaded
                    outcome.uploaded_dropbox += result.uploaded_dropbox
                    outcome.skipped += result.skipped
                    outcome.failed += result.failed
                except BrytonSyncError as exc:
                    outcome.errors.append(str(exc))
                    report(f"✗ Bryton: {exc}")
                except Exception as exc:  # noqa: BLE001 — surface unexpected failures
                    outcome.errors.append(str(exc))
                    report(f"✗ Bryton unexpected error: {exc}")
    finally:
        end_sync()

    return outcome


async def load_sync_secrets(
    store: secrets_module.SecretStore,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Return (igp_password, bryton_password, api_key, dropbox_refresh_token)."""
    igp_password = await store.get(secrets_module.IGP_PASSWORD)
    bryton_password = await store.get(secrets_module.BRYTON_PASSWORD)
    api_key = await store.get(secrets_module.INTERVALS_API_KEY)
    dropbox_refresh_token = await store.get(secrets_module.DROPBOX_REFRESH_TOKEN)
    return igp_password, bryton_password, api_key, dropbox_refresh_token
