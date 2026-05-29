"""Flet application entry point and view routing."""

from __future__ import annotations

import asyncio
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

    async def open_releases(_: ft.ControlEvent) -> None:
        # page.launch_url is a coroutine in Flet 0.85 — it must be awaited,
        # otherwise the "View" button silently does nothing.
        await page.launch_url(RELEASES_PAGE)

    def notify_update(latest: str | None, *, quiet_when_current: bool) -> None:
        # Must run on the event loop (not a worker thread) so the snackbar's
        # action handler is wired up and the "View" button works.
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
        page.pop_dialog()  # close the About dialog
        # allow_dev=True so it works on local/dev builds too (for testing): a
        # 0.0.0 dev build counts as older than any published release.
        latest = await asyncio.to_thread(check_for_update, __version__, allow_dev=True)
        notify_update(latest, quiet_when_current=False)

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
                    ft.TextButton("Check for updates", on_click=check_updates_now),
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

    # Quietly check GitHub for a newer release. The network call runs in a
    # thread (so it doesn't block the UI) but the snackbar is shown back on the
    # event loop — otherwise its action handler isn't wired and "View" is dead.
    # No-op on dev builds, silent on any error.
    async def auto_check_updates() -> None:
        latest = await asyncio.to_thread(check_for_update, __version__)
        notify_update(latest, quiet_when_current=True)

    page.run_task(auto_check_updates)


def main() -> None:
    ft.run(_app)


if __name__ == "__main__":
    main()
