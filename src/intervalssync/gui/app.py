"""Flet application entry point and view routing."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import flet as ft
from flet_permission_handler import Permission, PermissionHandler, PermissionStatus
from flet_secure_storage import SecureStorage

from .. import __version__
from . import config as config_module
from . import secrets as secrets_module
from .update_check import RELEASES_PAGE, check_for_update
from .settings_view import build_settings_view
from .sync_view import build_sync_view
from . import profile_sync_ui
from . import theme


_DESKTOP = {ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS, ft.PagePlatform.LINUX}
_MOBILE = {ft.PagePlatform.ANDROID, ft.PagePlatform.ANDROID_TV, ft.PagePlatform.IOS}
_PERMISSION_HANDLER_PLATFORMS = {
    ft.PagePlatform.ANDROID,
    ft.PagePlatform.ANDROID_TV,
    ft.PagePlatform.IOS,
    ft.PagePlatform.WINDOWS,
    *([ft.PagePlatform.WEB] if hasattr(ft.PagePlatform, "WEB") else []),
}
# Standard public Downloads directory on Android (the filesystem name is the
# singular "Download"). Used when the user opts in and grants storage access.
ANDROID_DOWNLOADS = "/storage/emulated/0/Download/intervalssync-fit"

APP_TITLE = "Intervals Sync"
APP_ICON = "icon.png"


def _assets_dir() -> str:
    dev_assets = Path(__file__).resolve().parents[3] / "assets"
    if dev_assets.is_dir():
        return str(dev_assets)
    return "assets"

_TAB_SYNC = 0
_TAB_SETTINGS = 1


async def _has_credentials(
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
) -> bool:
    if config.enable_igpsport and config.igp_user and await store.get(secrets_module.IGP_PASSWORD):
        return True
    if config.enable_bryton and config.bryton_user and await store.get(secrets_module.BRYTON_PASSWORD):
        return True
    return False


def _supports_permission_handler(platform: ft.PagePlatform) -> bool:
    return platform in _PERMISSION_HANDLER_PLATFORMS


def _secret_store_for_platform(
    platform: ft.PagePlatform,
) -> tuple[secrets_module.SecretStore, SecureStorage | None]:
    if platform == ft.PagePlatform.MACOS:
        return secrets_module.MacOSKeychainStore(), None

    storage = SecureStorage()
    return secrets_module.FletSecureStorage(storage), storage


async def _app(page: ft.Page) -> None:
    page.title = APP_TITLE
    page.theme_mode = ft.ThemeMode.SYSTEM
    theme.apply_page_theme(page)
    page.padding = 0
    page.bgcolor = theme.palette(page)["bg"]

    if page.platform in _DESKTOP:
        page.window.width = 600
        page.window.height = 760
        page.window.min_width = 400
        page.window.min_height = 560

    config = config_module.load()

    store, storage = _secret_store_for_platform(page.platform)
    perms = PermissionHandler() if _supports_permission_handler(page.platform) else None
    if storage is not None:
        page.services.append(storage)
    if perms is not None:
        page.services.append(perms)

    def _private_download_dir() -> str:
        base = os.getenv("FLET_APP_STORAGE_DATA") or tempfile.gettempdir()
        return str(Path(base) / "intervalssync-fit")

    async def apply_download_location() -> None:
        if page.platform not in _MOBILE:
            return
        config.download_dir = _private_download_dir()
        if config.save_to_downloads:
            try:
                status = await perms.get_status(Permission.MANAGE_EXTERNAL_STORAGE)
            except Exception:  # noqa: BLE001 — never let this break startup
                status = None
            if status == PermissionStatus.GRANTED:
                config.download_dir = ANDROID_DOWNLOADS

    await apply_download_location()

    body = ft.Container(expand=True)
    header_slot = ft.Container()
    current_tab = _TAB_SYNC
    is_mobile = page.platform in _MOBILE

    def _refresh_bg() -> None:
        page.bgcolor = theme.palette(page)["bg"]

    def _scrollable(view: ft.Control) -> ft.Control:
        return ft.Column([view], scroll=ft.ScrollMode.AUTO, expand=True)

    async def open_releases(_: ft.ControlEvent) -> None:
        await page.launch_url(RELEASES_PAGE)

    def notify_update(latest: str | None, *, quiet_when_current: bool) -> None:
        if latest:
            page.show_dialog(
                ft.SnackBar(
                    content=ft.Text(f"Update available: v{latest}"),
                    action="View",
                    on_action=open_releases,
                    duration=8000,
                )
            )
        elif not quiet_when_current:
            page.show_dialog(ft.SnackBar(ft.Text("You're on the latest version.")))
        page.update()

    async def check_updates_now(_: ft.ControlEvent) -> None:
        page.pop_dialog()
        latest = await asyncio.to_thread(check_for_update, __version__, allow_dev=True)
        notify_update(latest, quiet_when_current=False)

    def show_about(_: ft.ControlEvent | None = None) -> None:
        colors = theme.palette(page)
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_MD),
                title=theme.display_text("About", size=22),
                content=ft.Column(
                    tight=True,
                    spacing=theme.SPACE_SM,
                    controls=[
                        ft.Text(
                            APP_TITLE,
                            weight=ft.FontWeight.W_600,
                            color=colors["text"],
                        ),
                        ft.Text(
                            f"Version {__version__}",
                            size=13,
                            color=colors["text_muted"],
                        ),
                        ft.Text(
                            "Sync rides and planned workouts between iGPSPORT, "
                            "Bryton Active, and intervals.icu.",
                            size=13,
                            color=colors["text_muted"],
                        ),
                    ],
                ),
                actions=[
                    ft.TextButton("Check for updates", on_click=check_updates_now),
                    ft.TextButton(
                        "GitHub",
                        url="https://github.com/jorge-huxley/intervalssync",
                    ),
                    ft.TextButton("Close", on_click=lambda _: page.pop_dialog()),
                ],
            )
        )

    def _header() -> ft.Container:
        colors = theme.palette(page)
        return ft.Container(
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=theme.SPACE_SM,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=36,
                                height=36,
                                border_radius=theme.RADIUS_SM,
                                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                                content=ft.Image(
                                    src=APP_ICON,
                                    width=36,
                                    height=36,
                                    fit=ft.BoxFit.COVER,
                                ),
                            ),
                            ft.Column(
                                spacing=0,
                                controls=[
                                    theme.display_text(APP_TITLE, size=18, color=colors["text"]),
                                    ft.Text(
                                        "iGPSPORT · Bryton · intervals.icu",
                                        size=11,
                                        color=colors["text_muted"],
                                    ),
                                ],
                            ),
                        ],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.INFO_OUTLINE,
                        tooltip="About",
                        icon_color=colors["text_muted"],
                        on_click=show_about,
                    ),
                ],
            ),
            padding=ft.Padding(
                theme.SPACE_LG,
                theme.SPACE_MD,
                theme.SPACE_LG,
                theme.SPACE_MD,
            ),
            bgcolor=colors["bg"],
            border=ft.Border(bottom=ft.BorderSide(1, colors["border"])),
        )

    async def show_sync(_: ft.ControlEvent | None = None) -> None:
        nonlocal current_tab
        current_tab = _TAB_SYNC
        body.content = _scrollable(build_sync_view(page, config, store))
        header_slot.content = _header()
        _update_nav()
        _refresh_bg()
        page.update()

    async def show_settings(_: ft.ControlEvent | None = None) -> None:
        nonlocal current_tab
        current_tab = _TAB_SETTINGS

        async def on_profile_sync_check() -> None:
            await profile_sync_ui.prompt_if_needed(page, config, store)

        body.content = _scrollable(
            await build_settings_view(
                page,
                config,
                store,
                on_saved=show_sync,
                perms=perms,
                apply_download_location=apply_download_location,
                on_profile_sync_check=on_profile_sync_check,
            )
        )
        header_slot.content = _header()
        _update_nav()
        _refresh_bg()
        page.update()

    sync_tab = ft.TextButton("Sync", on_click=show_sync)
    settings_tab = ft.TextButton("Settings", on_click=show_settings)
    desktop_tabs = ft.Container(
        content=ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[sync_tab, settings_tab],
        ),
        padding=ft.Padding(0, theme.SPACE_SM, 0, theme.SPACE_SM),
    )

    def _update_nav() -> None:
        colors = theme.palette(page)
        for idx, btn in enumerate((sync_tab, settings_tab)):
            active = idx == current_tab
            btn.style = ft.ButtonStyle(
                color=colors["accent"] if active else colors["text_muted"],
                bgcolor=colors["accent_soft"] if active else ft.Colors.TRANSPARENT,
                shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_SM),
                padding=ft.Padding(
                    theme.SPACE_MD, theme.SPACE_SM, theme.SPACE_MD, theme.SPACE_SM
                ),
            )

    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    header_slot,
                    desktop_tabs,
                    ft.Container(
                        content=body,
                        expand=True,
                        padding=ft.Padding(
                            theme.SPACE_LG,
                            theme.SPACE_MD,
                            theme.SPACE_LG,
                            theme.SPACE_LG if not is_mobile else theme.SPACE_MD,
                        ),
                    ),
                ],
            ),
        )
    )

    if await _has_credentials(config, store):
        await show_sync()
    else:
        await show_settings()

    async def auto_check_updates() -> None:
        latest = await asyncio.to_thread(check_for_update, __version__)
        notify_update(latest, quiet_when_current=True)

    async def auto_check_profile_sync() -> None:
        if not config.enable_igpsport or not config.profile_sync_check_on_launch:
            return
        await profile_sync_ui.prompt_if_needed(page, config, store)

    page.run_task(auto_check_updates)
    page.run_task(auto_check_profile_sync)


def main() -> None:
    ft.run(_app, assets_dir=_assets_dir())


if __name__ == "__main__":
    main()
