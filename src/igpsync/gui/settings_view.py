"""Settings view: enter credentials and have them saved to the OS vault."""

from __future__ import annotations

from typing import Awaitable, Callable

import flet as ft

from .. import config as config_module
from .. import secrets as secrets_module
from ..core import CYCLING_ACTIVITY_TYPES
from .system import open_folder


async def build_settings_view(
    page: ft.Page,
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
    on_saved: Callable[[], Awaitable[None]],
) -> ft.Control:
    """Return the settings card. `on_saved` is awaited after a successful save."""

    # Prefetch the currently-stored secrets to prefill the fields.
    existing_password = await store.get(secrets_module.IGP_PASSWORD) or ""
    existing_api_key = await store.get(secrets_module.INTERVALS_API_KEY) or ""

    igp_user = ft.TextField(
        label="iGPSPORT email",
        value=config.igp_user,
        prefix_icon=ft.Icons.PERSON,
        autofocus=not config.igp_user,
    )
    igp_password = ft.TextField(
        label="iGPSPORT password",
        value=existing_password,
        prefix_icon=ft.Icons.LOCK,
        password=True,
        can_reveal_password=True,
    )
    api_key = ft.TextField(
        label="intervals.icu API key",
        value=existing_api_key,
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

    activity_type = ft.Dropdown(
        label="Activity type on intervals.icu",
        value=config.activity_type,
        width=320,
        options=[
            ft.dropdown.Option(key="", text="Don't change (leave as uploaded)"),
            *(
                ft.dropdown.Option(key=value, text=label)
                for value, label in CYCLING_ACTIVITY_TYPES
            ),
        ],
    )

    delete_after_upload = ft.Switch(
        label="Delete downloaded files after upload",
        value=config.delete_after_upload,
    )

    force_resync = ft.Switch(
        label="Force re-sync (re-download even if already on intervals.icu)",
        value=config.force_resync,
    )

    download_folder_row = ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Icon(ft.Icons.FOLDER, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    ft.Text("Download folder", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                    ft.Text(config.download_dir, size=13, selectable=True, no_wrap=False),
                ],
            ),
            ft.IconButton(
                ft.Icons.FOLDER_OPEN,
                tooltip="Open folder",
                on_click=lambda _: open_folder(config.download_dir),
            ),
        ],
    )

    # Developer options — pick which pipeline steps run. Each step builds on
    # the previous one (upload needs a download, which needs the FIT URL).
    step_list = ft.Switch(label="List activities", value=config.step_list_activities)
    step_url = ft.Switch(label="Resolve download URLs", value=config.step_get_download_url)
    step_download = ft.Switch(label="Download .fit files", value=config.step_download_fit)
    step_upload = ft.Switch(label="Upload to intervals.icu", value=config.step_upload_intervals)

    developer_options = ft.ExpansionTile(
        title=ft.Text("Developer options"),
        leading=ft.Icon(ft.Icons.DEVELOPER_MODE),
        affinity=ft.TileAffinity.LEADING,
        expanded=False,
        controls=[
            ft.Container(
                padding=ft.Padding(left=16, top=0, right=16, bottom=8),
                content=ft.Column(
                    spacing=4,
                    controls=[
                        ft.Text(
                            "Choose which steps run during a sync. Each step depends "
                            "on the ones above it.",
                            size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                        step_list,
                        step_url,
                        step_download,
                        step_upload,
                    ],
                ),
            )
        ],
    )

    async def save(_: ft.ControlEvent) -> None:
        if not igp_user.value or not igp_password.value:
            page.show_dialog(ft.SnackBar(ft.Text("iGPSPORT email and password are required.")))
            return

        config.igp_user = igp_user.value.strip()
        try:
            config.max_activities = max(1, int(max_activities.value))
        except (TypeError, ValueError):
            config.max_activities = 5
            max_activities.value = "5"
        config.delete_after_upload = delete_after_upload.value
        config.force_resync = force_resync.value
        config.activity_type = activity_type.value or ""
        config.step_list_activities = step_list.value
        config.step_get_download_url = step_url.value
        config.step_download_fit = step_download.value
        config.step_upload_intervals = step_upload.value
        config_module.save(config)

        await store.set(secrets_module.IGP_PASSWORD, igp_password.value)
        if api_key.value:
            await store.set(secrets_module.INTERVALS_API_KEY, api_key.value)
        else:
            await store.delete(secrets_module.INTERVALS_API_KEY)

        page.show_dialog(ft.SnackBar(ft.Text("Saved securely to your system credential store.")))
        await on_saved()

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
                    activity_type,
                    delete_after_upload,
                    force_resync,
                    download_folder_row,
                    developer_options,
                    ft.FilledButton(
                        "Save",
                        icon=ft.Icons.SAVE,
                        on_click=save,
                    ),
                ],
            ),
        ),
    )
