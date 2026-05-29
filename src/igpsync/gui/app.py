"""Flet application entry point and view routing."""

from __future__ import annotations

import flet as ft

from .. import config as config_module
from .. import secrets as secrets_module
from .settings_view import build_settings_view
from .sync_view import build_sync_view


def _app(page: ft.Page) -> None:
    page.title = "iGPSPORT → intervals.icu"
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.window.width = 560
    page.window.height = 720
    page.window.min_width = 420
    page.padding = 0

    config = config_module.load()
    store = secrets_module.KeyringSecretStore()

    body = ft.Container(expand=True, padding=20)

    def show_sync() -> None:
        body.content = build_sync_view(page, config, store)
        page.update()

    def show_settings() -> None:
        body.content = build_settings_view(page, config, store, on_saved=show_sync)
        page.update()

    page.appbar = ft.AppBar(
        title=ft.Text("iGPSPORT → intervals.icu"),
        center_title=False,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        actions=[
            ft.IconButton(ft.Icons.SYNC, tooltip="Sync", on_click=lambda _: show_sync()),
            ft.IconButton(
                ft.Icons.SETTINGS, tooltip="Settings", on_click=lambda _: show_settings()
            ),
        ],
    )

    page.add(body)

    # First run (no credentials yet) opens Settings; otherwise go to Sync.
    if config.igp_user and store.get(secrets_module.IGP_PASSWORD):
        show_sync()
    else:
        show_settings()


def main() -> None:
    ft.run(_app)


if __name__ == "__main__":
    main()
