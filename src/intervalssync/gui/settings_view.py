"""Settings view: enter credentials and have them saved to the OS vault."""

from __future__ import annotations

from typing import Awaitable, Callable

import flet as ft
from flet_permission_handler import Permission, PermissionHandler, PermissionStatus

from . import config as config_module
from . import secrets as secrets_module
from ..igpsport.core import CYCLING_ACTIVITY_TYPES
from ..dropbox_client import (
    DEFAULT_DROPBOX_FOLDER,
    finish_dropbox_auth,
    get_dropbox_app_key,
    start_dropbox_auth,
)
from .system import open_folder


_NARROW_FIELD_WIDTH = 220


def _narrow_number_field(
    label: str,
    value: str,
    icon: str | None,
    caption: str,
) -> tuple[ft.TextField, ft.Column]:
    """Compact numeric input (phone-width) with a full-width caption below."""
    field = ft.TextField(
        label=label,
        value=value,
        prefix_icon=icon,
        keyboard_type=ft.KeyboardType.NUMBER,
        width=_NARROW_FIELD_WIDTH,
    )
    block = ft.Column(
        spacing=4,
        tight=True,
        controls=[
            field,
            ft.Text(
                caption,
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ],
    )
    return field, block


def _developer_step_controls(config: config_module.AppConfig) -> list[ft.Control]:
    """Pipeline step toggles — not shown in Settings; kept for local/dev use."""
    return [
        ft.Switch(label="List activities", value=config.step_list_activities),
        ft.Switch(label="Resolve download URLs", value=config.step_get_download_url),
        ft.Switch(label="Download .fit files", value=config.step_download_fit),
        ft.Switch(label="Upload to intervals.icu", value=config.step_upload_intervals),
    ]


async def build_settings_view(
    page: ft.Page,
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
    on_saved: Callable[[], Awaitable[None]],
    perms: PermissionHandler | None = None,
    apply_download_location: Callable[[], Awaitable[None]] | None = None,
) -> ft.Control:
    """Return the settings card. `on_saved` is awaited after a successful save."""

    existing_igp_password = await store.get(secrets_module.IGP_PASSWORD) or ""
    existing_bryton_password = await store.get(secrets_module.BRYTON_PASSWORD) or ""
    existing_api_key = await store.get(secrets_module.INTERVALS_API_KEY) or ""
    existing_dropbox_token = await store.get(secrets_module.DROPBOX_REFRESH_TOKEN)
    dropbox_app_key = get_dropbox_app_key()

    enable_igpsport = ft.Switch(
        label="Enable iGPSPORT",
        value=config.enable_igpsport,
    )
    igp_user = ft.TextField(
        label="iGPSPORT email",
        value=config.igp_user,
        prefix_icon=ft.Icons.PERSON,
    )
    igp_password = ft.TextField(
        label="iGPSPORT password",
        value=existing_igp_password,
        prefix_icon=ft.Icons.LOCK,
        password=True,
        can_reveal_password=True,
    )

    enable_bryton = ft.Switch(
        label="Enable Bryton Active",
        value=config.enable_bryton,
    )
    bryton_user = ft.TextField(
        label="Bryton Active email",
        value=config.bryton_user,
        prefix_icon=ft.Icons.PERSON,
    )
    bryton_password = ft.TextField(
        label="Bryton Active password",
        value=existing_bryton_password,
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

    max_activities, max_activities_block = _narrow_number_field(
        "Activities",
        str(config.max_activities),
        ft.Icons.FORMAT_LIST_NUMBERED,
        "Number of recent activities to sync on each run.",
    )

    workout_days_ahead, workout_days_ahead_block = _narrow_number_field(
        "Days ahead",
        str(config.workout_days_ahead),
        ft.Icons.CALENDAR_MONTH,
        "Planned workouts from intervals.icu to upload to iGPSPORT. 1 = today only.",
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
        label="Force re-sync (re-download even if already uploaded)",
        value=config.force_resync,
    )

    upload_dropbox = ft.Switch(
        label="Upload activities to Dropbox",
        value=(
            config.upload_dropbox
            and bool(existing_dropbox_token)
            and bool(dropbox_app_key)
        ),
        disabled=not bool(existing_dropbox_token and dropbox_app_key),
    )
    dropbox_folder = ft.TextField(
        label="Dropbox folder",
        value=config.dropbox_folder or DEFAULT_DROPBOX_FOLDER,
        prefix_icon=ft.Icons.FOLDER,
        helper="Dropbox path, e.g. /Fit files",
    )
    dropbox_date_filenames = ft.Switch(
        label="Use date in Dropbox filenames",
        value=config.dropbox_date_filenames,
    )
    dropbox_status = ft.Text(
        (
            "Connected"
            if existing_dropbox_token and dropbox_app_key
            else "Dropbox app key missing from this build"
            if not dropbox_app_key
            else "Not connected"
        ),
        size=13,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    dropbox_auth_code = ft.TextField(
        label="Dropbox authorization code",
        prefix_icon=ft.Icons.KEY,
        visible=False,
    )
    dropbox_finish_button = ft.OutlinedButton(
        "Finish connection",
        icon=ft.Icons.CHECK,
        visible=False,
    )
    dropbox_auth_flow = None

    async def connect_dropbox(_: ft.ControlEvent) -> None:
        nonlocal dropbox_auth_flow
        if not dropbox_app_key:
            page.show_dialog(
                ft.SnackBar(ft.Text("Dropbox app key is missing from this build."))
            )
            return
        dropbox_auth_flow, auth_url = start_dropbox_auth(dropbox_app_key)
        dropbox_auth_code.visible = True
        dropbox_finish_button.visible = True
        dropbox_auth_code.value = ""
        await page.launch_url(auth_url)
        page.show_dialog(
            ft.SnackBar(ft.Text("Paste the Dropbox authorization code here."))
        )
        page.update()

    async def finish_dropbox(_: ft.ControlEvent) -> None:
        nonlocal dropbox_auth_flow
        if dropbox_auth_flow is None:
            page.show_dialog(ft.SnackBar(ft.Text("Start Dropbox connection first.")))
            return
        if not dropbox_auth_code.value:
            page.show_dialog(ft.SnackBar(ft.Text("Paste the Dropbox code first.")))
            return
        try:
            refresh_token = finish_dropbox_auth(
                dropbox_auth_flow, dropbox_auth_code.value
            )
        except Exception as exc:  # noqa: BLE001 — show auth failures directly
            page.show_dialog(ft.SnackBar(ft.Text(f"Dropbox connection failed: {exc}")))
            return
        if not refresh_token:
            page.show_dialog(
                ft.SnackBar(ft.Text("Dropbox did not return a refresh token."))
            )
            return
        await store.set(secrets_module.DROPBOX_REFRESH_TOKEN, refresh_token)
        dropbox_auth_flow = None
        dropbox_auth_code.visible = False
        dropbox_finish_button.visible = False
        dropbox_status.value = "Connected"
        upload_dropbox.disabled = False
        upload_dropbox.value = True
        dropbox_disconnect_button.disabled = False
        page.show_dialog(ft.SnackBar(ft.Text("Dropbox connected.")))
        page.update()

    async def disconnect_dropbox(_: ft.ControlEvent) -> None:
        await store.delete(secrets_module.DROPBOX_REFRESH_TOKEN)
        config.upload_dropbox = False
        config_module.save(config)
        upload_dropbox.value = False
        upload_dropbox.disabled = True
        dropbox_status.value = "Not connected"
        page.show_dialog(ft.SnackBar(ft.Text("Dropbox disconnected.")))
        page.update()

    dropbox_connect_button = ft.OutlinedButton(
        "Connect Dropbox",
        icon=ft.Icons.CLOUD_UPLOAD,
        disabled=not bool(dropbox_app_key),
        on_click=connect_dropbox,
    )
    dropbox_disconnect_button = ft.TextButton(
        "Disconnect",
        icon=ft.Icons.LINK_OFF,
        disabled=not bool(existing_dropbox_token),
        on_click=disconnect_dropbox,
    )
    dropbox_finish_button.on_click = finish_dropbox

    dropbox_options = ft.ExpansionTile(
        title=ft.Text("Dropbox"),
        leading=ft.Icon(ft.Icons.CLOUD),
        affinity=ft.TileAffinity.LEADING,
        expanded=config.upload_dropbox,
        controls=[
            ft.Container(
                padding=ft.Padding(left=16, top=0, right=16, bottom=8),
                content=ft.Column(
                    spacing=8,
                    controls=[
                        dropbox_status,
                        ft.Row(
                            spacing=8,
                            controls=[
                                dropbox_connect_button,
                                dropbox_disconnect_button,
                            ],
                        ),
                        dropbox_auth_code,
                        dropbox_finish_button,
                        upload_dropbox,
                        dropbox_folder,
                        dropbox_date_filenames,
                    ],
                ),
            )
        ],
    )

    is_mobile = page.platform in {
        ft.PagePlatform.ANDROID,
        ft.PagePlatform.ANDROID_TV,
        ft.PagePlatform.IOS,
    }

    save_to_downloads = ft.Switch(
        label="Save to phone's Downloads folder",
        value=config.save_to_downloads,
    )

    if is_mobile:
        if config.save_to_downloads:
            note = "Saved to your phone's Downloads folder (Download/intervalssync-fit)."
        else:
            note = (
                "Kept in the app's private storage and uploaded to intervals.icu "
                "(removed afterwards unless you turn that off). Turn on “Save to "
                "phone's Downloads folder” to keep them where you can find them."
            )
        folder_detail = ft.Text(note, size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        folder_trailing: ft.Control | None = None
    else:
        folder_detail = ft.Text(
            config.download_dir, size=13, selectable=True, no_wrap=False
        )
        folder_trailing = ft.IconButton(
            ft.Icons.FOLDER_OPEN,
            tooltip="Open folder",
            on_click=lambda _: open_folder(config.download_dir),
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
                    folder_detail,
                ],
            ),
            *( [folder_trailing] if folder_trailing else [] ),
        ],
    )

    igp_credentials = ft.Column(
        spacing=8,
        controls=[igp_user, igp_password],
    )
    bryton_credentials = ft.Column(
        spacing=8,
        controls=[bryton_user, bryton_password],
    )
    workout_sync_section = ft.Column(
        spacing=12,
        visible=config.enable_igpsport,
        controls=[
            ft.Divider(),
            ft.Text("Workout sync options", size=16, weight=ft.FontWeight.BOLD),
            workout_days_ahead_block,
        ],
    )
    dropbox_section = ft.Container(
        visible=config.enable_igpsport,
        content=dropbox_options,
    )

    def update_source_visibility(_: ft.ControlEvent | None = None) -> None:
        igp_credentials.visible = bool(enable_igpsport.value)
        workout_sync_section.visible = bool(enable_igpsport.value)
        dropbox_section.visible = bool(enable_igpsport.value)
        bryton_credentials.visible = bool(enable_bryton.value)
        page.update()

    enable_igpsport.on_change = update_source_visibility
    enable_bryton.on_change = update_source_visibility
    update_source_visibility()

    async def save(_: ft.ControlEvent) -> None:
        if not enable_igpsport.value and not enable_bryton.value:
            page.show_dialog(
                ft.SnackBar(ft.Text("Enable at least one activity source."))
            )
            return

        igp_pw = igp_password.value or existing_igp_password
        bryton_pw = bryton_password.value or existing_bryton_password

        if enable_igpsport.value:
            if not igp_user.value.strip():
                page.show_dialog(
                    ft.SnackBar(ft.Text("iGPSPORT email is required when enabled."))
                )
                return
            if not igp_pw:
                page.show_dialog(
                    ft.SnackBar(ft.Text("iGPSPORT password is required when enabled."))
                )
                return

        if enable_bryton.value:
            if not bryton_user.value.strip():
                page.show_dialog(
                    ft.SnackBar(ft.Text("Bryton Active email is required when enabled."))
                )
                return
            if not bryton_pw:
                page.show_dialog(
                    ft.SnackBar(ft.Text("Bryton Active password is required when enabled."))
                )
                return

        config.enable_igpsport = bool(enable_igpsport.value)
        config.enable_bryton = bool(enable_bryton.value)
        config.igp_user = igp_user.value.strip()
        config.bryton_user = bryton_user.value.strip()
        try:
            config.max_activities = max(1, int(max_activities.value))
        except (TypeError, ValueError):
            config.max_activities = 5
            max_activities.value = "5"
        try:
            config.workout_days_ahead = max(1, int(workout_days_ahead.value))
        except (TypeError, ValueError):
            config.workout_days_ahead = 1
            workout_days_ahead.value = "1"
        config.delete_after_upload = delete_after_upload.value
        config.force_resync = force_resync.value
        config.activity_type = activity_type.value or ""
        config.dropbox_folder = dropbox_folder.value.strip() or DEFAULT_DROPBOX_FOLDER
        config.dropbox_date_filenames = bool(dropbox_date_filenames.value)
        config.upload_dropbox = bool(upload_dropbox.value)

        message = "Saved securely to your system credential store."
        if config.upload_dropbox and not dropbox_app_key:
            config.upload_dropbox = False
            upload_dropbox.value = False
            message = "Saved, but Dropbox is disabled because this build has no app key."
        elif config.upload_dropbox and not await store.get(
            secrets_module.DROPBOX_REFRESH_TOKEN
        ):
            config.upload_dropbox = False
            upload_dropbox.value = False
            message = "Saved, but Dropbox is disabled until you connect it."
        if is_mobile:
            want_downloads = bool(save_to_downloads.value)
            if want_downloads and perms is not None:
                status = await perms.request(Permission.MANAGE_EXTERNAL_STORAGE)
                if status != PermissionStatus.GRANTED:
                    want_downloads = False
                    save_to_downloads.value = False
                    message = (
                        "Saved, but storage permission wasn't granted — files "
                        "stay in the app's private storage."
                    )
            config.save_to_downloads = want_downloads
        config_module.save(config)

        if igp_password.value:
            await store.set(secrets_module.IGP_PASSWORD, igp_password.value)
        if bryton_password.value:
            await store.set(secrets_module.BRYTON_PASSWORD, bryton_password.value)
        if api_key.value:
            await store.set(secrets_module.INTERVALS_API_KEY, api_key.value)
        else:
            await store.delete(secrets_module.INTERVALS_API_KEY)

        if apply_download_location is not None:
            await apply_download_location()

        page.show_dialog(ft.SnackBar(ft.Text(message)))
        await on_saved()

    return ft.Card(
        content=ft.Container(
            padding=24,
            content=ft.Column(
                spacing=16,
                controls=[
                    ft.Text("Settings", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "Passwords and API keys are stored in your operating "
                        "system's secure credential vault, never in a file.",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    api_key,
                    ft.Divider(),
                    ft.Text("iGPSPORT", size=16, weight=ft.FontWeight.BOLD),
                    enable_igpsport,
                    igp_credentials,
                    ft.Divider(),
                    ft.Text("Bryton Active", size=16, weight=ft.FontWeight.BOLD),
                    enable_bryton,
                    bryton_credentials,
                    ft.Divider(),
                    ft.Text("Activity sync options", size=16, weight=ft.FontWeight.BOLD),
                    max_activities_block,
                    activity_type,
                    delete_after_upload,
                    force_resync,
                    workout_sync_section,
                    dropbox_section,
                    *([save_to_downloads] if is_mobile else []),
                    download_folder_row,
                    ft.FilledButton(
                        "Save",
                        icon=ft.Icons.SAVE,
                        on_click=save,
                    ),
                ],
            ),
        ),
    )
