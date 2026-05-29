"""Settings view: enter credentials and have them saved to the OS vault."""

from __future__ import annotations

from typing import Callable

import flet as ft

from .. import config as config_module
from .. import secrets as secrets_module


def build_settings_view(
    page: ft.Page,
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
    on_saved: Callable[[], None],
) -> ft.Control:
    """Return the settings card. `on_saved` is called after a successful save."""

    igp_user = ft.TextField(
        label="iGPSPORT email",
        value=config.igp_user,
        prefix_icon=ft.Icons.PERSON,
        autofocus=not config.igp_user,
    )
    igp_password = ft.TextField(
        label="iGPSPORT password",
        value=store.get(secrets_module.IGP_PASSWORD) or "",
        prefix_icon=ft.Icons.LOCK,
        password=True,
        can_reveal_password=True,
    )
    api_key = ft.TextField(
        label="intervals.icu API key",
        value=store.get(secrets_module.INTERVALS_API_KEY) or "",
        prefix_icon=ft.Icons.KEY,
        password=True,
        can_reveal_password=True,
        helper="Settings → Developer on intervals.icu",
    )

    max_activities = ft.TextField(
        label="Activities to sync",
        value=str(config.max_activities),
        prefix_icon=ft.Icons.FORMAT_LIST_NUMBERED,
        keyboard_type=ft.KeyboardType.NUMBER,
        width=220,
    )

    def save(_: ft.ControlEvent) -> None:
        if not igp_user.value or not igp_password.value:
            page.show_dialog(ft.SnackBar(ft.Text("iGPSPORT email and password are required.")))
            return

        config.igp_user = igp_user.value.strip()
        try:
            config.max_activities = max(1, int(max_activities.value))
        except (TypeError, ValueError):
            config.max_activities = 5
            max_activities.value = "5"
        config_module.save(config)

        store.set(secrets_module.IGP_PASSWORD, igp_password.value)
        if api_key.value:
            store.set(secrets_module.INTERVALS_API_KEY, api_key.value)
        else:
            store.delete(secrets_module.INTERVALS_API_KEY)

        page.show_dialog(ft.SnackBar(ft.Text("Saved securely to your system credential store.")))
        on_saved()

    return ft.Card(
        content=ft.Container(
            padding=24,
            content=ft.Column(
                spacing=16,
                controls=[
                    ft.Text("Account", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "Your password and API key are stored in your operating "
                        "system's secure credential vault, never in a file.",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    igp_user,
                    igp_password,
                    api_key,
                    max_activities,
                    ft.FilledButton(
                        "Save",
                        icon=ft.Icons.SAVE,
                        on_click=save,
                    ),
                ],
            ),
        ),
    )
