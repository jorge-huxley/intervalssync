"""Flet application entry point and view routing."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import flet as ft
from flet_secure_storage import SecureStorage

from .. import __version__
from .. import config as config_module
from .. import secrets as secrets_module
from ..update_check import RELEASES_PAGE, check_for_update
from .settings_view import build_settings_view
from .sync_view import build_sync_view


_DESKTOP = {ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS, ft.PagePlatform.LINUX}
_MOBILE = {ft.PagePlatform.ANDROID, ft.PagePlatform.ANDROID_TV, ft.PagePlatform.IOS}


async def _app(page: ft.Page) -> None:
    page.title = "iGPSPORT → intervals.icu"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.padding = 0

    # Window sizing only applies on desktop; on mobile the app fills the screen.
    if page.platform in _DESKTOP:
        page.window.width = 560
        page.window.height = 720
        page.window.min_width = 420

    config = config_module.load()

    # On mobile the public Downloads dir isn't writable (scoped storage), so
    # download into the app's own writable storage instead. Flet sets
    # FLET_APP_STORAGE_DATA to a pre-created, writable per-app directory.
    if page.platform in _MOBILE:
        base = os.getenv("FLET_APP_STORAGE_DATA") or tempfile.gettempdir()
        config.download_dir = str(Path(base) / "igpsport-fit")

    # Register the secure-storage service and wrap it as our SecretStore.
    storage = SecureStorage()
    page.services.append(storage)
    store = secrets_module.FletSecureStorage(storage)

    body = ft.Container(expand=True, padding=20)

    def _scrollable(view: ft.Control) -> ft.Control:
        # Wrap the view so it scrolls when taller than the window instead of
        # being clipped (e.g. the full Settings form on a short window).
        return ft.Column([view], scroll=ft.ScrollMode.AUTO, expand=True)

    async def show_sync(_: ft.ControlEvent | None = None) -> None:
        body.content = _scrollable(build_sync_view(page, config, store))
        page.update()

    async def show_settings(_: ft.ControlEvent | None = None) -> None:
        body.content = _scrollable(
            await build_settings_view(page, config, store, on_saved=show_sync)
        )
        page.update()

    def show_about(_: ft.ControlEvent | None = None) -> None:
        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("About"),
                content=ft.Column(
                    tight=True,
                    spacing=6,
                    controls=[
                        ft.Text("iGPSPORT → intervals.icu", weight=ft.FontWeight.BOLD),
                        ft.Text(f"Version {__version__}"),
                    ],
                ),
                actions=[
                    ft.TextButton(
                        "GitHub",
                        url="https://github.com/jorge-huxley/igpsport-intervals",
                    ),
                    ft.TextButton("Close", on_click=lambda _: page.pop_dialog()),
                ],
            )
        )

    page.appbar = ft.AppBar(
        title=ft.Text("iGPSPORT → intervals.icu"),
        center_title=False,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        actions=[
            ft.IconButton(ft.Icons.SYNC, tooltip="Sync", on_click=show_sync),
            ft.IconButton(ft.Icons.SETTINGS, tooltip="Settings", on_click=show_settings),
            ft.IconButton(ft.Icons.INFO_OUTLINE, tooltip="About", on_click=show_about),
        ],
    )

    page.add(body)

    # First run (no credentials yet) opens Settings; otherwise go to Sync.
    if config.igp_user and await store.get(secrets_module.IGP_PASSWORD):
        await show_sync()
    else:
        await show_settings()

    # Quietly check GitHub for a newer release (off the UI thread; no-op on
    # dev builds, silent on any error).
    def _check_updates() -> None:
        latest = check_for_update(__version__)
        if latest:
            page.show_dialog(
                ft.SnackBar(
                    content=ft.Text(f"Update available: v{latest}"),
                    action="View",
                    on_action=lambda _: page.launch_url(RELEASES_PAGE),
                    duration=8000,
                )
            )
            page.update()

    page.run_thread(_check_updates)


def main() -> None:
    ft.run(_app)


if __name__ == "__main__":
    main()
