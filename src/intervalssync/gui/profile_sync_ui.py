"""GUI helpers for iGPSPORT profile / zone sync."""

from __future__ import annotations

import asyncio
from typing import Callable

import flet as ft

from ..igpsport.core import SyncError
from ..igpsport.profile_sync import (
    ProfileSyncConfig,
    ProfileSyncResult,
    ProfileThresholdStatus,
    fetch_profile_threshold_status,
    sync_profile_zones,
)
from . import config as config_module
from . import secrets as secrets_module
from . import theme


async def credentials_ready(
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
) -> tuple[str, str] | None:
    if not config.enable_igpsport or not config.igp_user:
        return None
    igp_password = await store.get(secrets_module.IGP_PASSWORD)
    api_key = await store.get(secrets_module.INTERVALS_API_KEY)
    if not igp_password or not api_key:
        return None
    return igp_password, api_key


def run_sync_profile_zones(
    config: config_module.AppConfig,
    igp_password: str,
    api_key: str,
    *,
    progress: Callable[[str], None] | None = None,
) -> ProfileSyncResult:
    sync_config = ProfileSyncConfig(
        igp_user=config.igp_user,
        igp_password=igp_password,
        intervals_api_key=api_key,
        igp_region=config.igp_region,
    )
    return sync_profile_zones(sync_config, progress=progress)


async def check_profile_thresholds(
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
) -> ProfileThresholdStatus | None:
    creds = await credentials_ready(config, store)
    if creds is None:
        return None
    igp_password, api_key = creds
    try:
        return await asyncio.to_thread(
            fetch_profile_threshold_status,
            ProfileSyncConfig(
                igp_user=config.igp_user,
                igp_password=igp_password,
                intervals_api_key=api_key,
                igp_region=config.igp_region,
            ),
        )
    except (SyncError, Exception):  # noqa: BLE001 — fail silent for background checks
        return None


def _should_prompt(
    config: config_module.AppConfig,
    status: ProfileThresholdStatus,
) -> bool:
    if not status.needs_sync:
        return False
    if (
        config.profile_sync_declined_fingerprint
        and status.intervals_fingerprint == config.profile_sync_declined_fingerprint
    ):
        return False
    return True


def _clear_declined_fingerprint(config: config_module.AppConfig) -> None:
    if config.profile_sync_declined_fingerprint:
        config.profile_sync_declined_fingerprint = ""
        config_module.save(config)


def _save_declined_fingerprint(
    config: config_module.AppConfig,
    status: ProfileThresholdStatus,
) -> None:
    config.profile_sync_declined_fingerprint = status.intervals_fingerprint
    config_module.save(config)


def _sync_success_message(result: ProfileSyncResult) -> str:
    if result.after is None:
        return "iGPSPORT profile updated."
    member = result.after.get("member")
    if not isinstance(member, dict):
        return "iGPSPORT profile updated."
    parts: list[str] = []
    for key, label in (("ftp", "FTP"), ("lthr", "LTHR"), ("mhr", "max HR")):
        if key in member:
            parts.append(f"{label} {member[key]}")
    if parts:
        return "iGPSPORT profile updated — " + ", ".join(parts) + "."
    return "iGPSPORT profile updated."


async def sync_with_feedback(
    page: ft.Page,
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
    *,
    clear_declined: bool = True,
) -> bool:
    creds = await credentials_ready(config, store)
    if creds is None:
        page.show_dialog(
            ft.SnackBar(
                ft.Text("Add iGPSPORT credentials and intervals.icu API key in Settings first.")
            )
        )
        page.update()
        return False

    igp_password, api_key = creds
    page.show_dialog(ft.SnackBar(ft.Text("Updating iGPSPORT profile…")))
    page.update()

    def _run_sync() -> tuple[bool, str]:
        try:
            result = run_sync_profile_zones(config, igp_password, api_key)
            return True, _sync_success_message(result)
        except SyncError as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user
            return False, f"Unexpected error: {exc}"

    ok, message = await asyncio.to_thread(_run_sync)
    if ok and clear_declined:
        _clear_declined_fingerprint(config)
    page.show_dialog(ft.SnackBar(ft.Text(message)))
    page.update()
    return ok


async def prompt_if_needed(
    page: ft.Page,
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
) -> None:
    if not config.enable_igpsport:
        return

    status = await check_profile_thresholds(config, store)
    if status is None or not _should_prompt(config, status):
        return

    colors = theme.palette(page)

    async def dismiss(_: ft.ControlEvent) -> None:
        page.pop_dialog()
        _save_declined_fingerprint(config, status)
        page.update()

    async def update_now(_: ft.ControlEvent) -> None:
        page.pop_dialog()
        page.update()
        await sync_with_feedback(page, config, store)

    difference_lines = [
        ft.Text(f"• {diff}", size=13, color=colors["text"])
        for diff in status.differences
    ]
    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_MD),
            title=theme.display_text("Update iGPSPORT profile?", size=20),
            content=ft.Column(
                tight=True,
                spacing=theme.SPACE_SM,
                controls=[
                    ft.Text(
                        "Your iGPSPORT thresholds differ from intervals.icu:",
                        size=13,
                        color=colors["text_muted"],
                    ),
                    *difference_lines,
                    ft.Text(
                        "Power and heart-rate zones will be updated too.",
                        size=12,
                        color=colors["text_muted"],
                    ),
                ],
            ),
            actions=[
                ft.TextButton("Not now", on_click=dismiss),
                ft.TextButton("Update now", on_click=update_now),
            ],
        )
    )
    page.update()


def format_threshold_status(status: ProfileThresholdStatus | None) -> str:
    if status is None:
        return "Could not check profile status."
    if not status.needs_sync:
        return "In sync with intervals.icu."
    if len(status.differences) == 1:
        return f"Out of sync: {status.differences[0]}"
    return "Out of sync: " + ", ".join(
        diff.split(":")[0] for diff in status.differences
    )
