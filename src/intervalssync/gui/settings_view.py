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
from . import theme
from . import profile_sync_ui
from .system import open_folder


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
    on_profile_sync_check: Callable[[], Awaitable[None]] | None = None,
) -> ft.Control:
    colors = theme.palette(page)

    existing_igp_password = await store.get(secrets_module.IGP_PASSWORD) or ""
    existing_bryton_password = await store.get(secrets_module.BRYTON_PASSWORD) or ""
    existing_api_key = await store.get(secrets_module.INTERVALS_API_KEY) or ""
    existing_dropbox_token = await store.get(secrets_module.DROPBOX_REFRESH_TOKEN)
    dropbox_app_key = get_dropbox_app_key()

    is_mobile = theme.is_mobile(page)

    def _input_field(**kwargs: object) -> ft.TextField:
        kwargs.setdefault("border_radius", theme.RADIUS_SM)
        if is_mobile:
            kwargs.setdefault("text_size", 14)
        return ft.TextField(**kwargs)

    enable_igpsport = ft.Switch(
        label="Enable iGPSPORT",
        value=config.enable_igpsport,
        active_color=colors["accent"],
    )
    igp_user = _input_field(
        label="iGPSPORT email",
        value=config.igp_user,
        prefix_icon=ft.Icons.PERSON_OUTLINED,
        autofocus=not config.igp_user,
    )
    igp_password = _input_field(
        label="iGPSPORT password",
        value=existing_igp_password,
        prefix_icon=ft.Icons.LOCK_OUTLINED,
        password=True,
        can_reveal_password=True,
    )

    enable_bryton = ft.Switch(
        label="Enable Bryton Active",
        value=config.enable_bryton,
        active_color=colors["accent"],
    )
    bryton_user = _input_field(
        label="Bryton Active email",
        value=config.bryton_user,
        prefix_icon=ft.Icons.PERSON_OUTLINED,
    )
    bryton_password = _input_field(
        label="Bryton Active password",
        value=existing_bryton_password,
        prefix_icon=ft.Icons.LOCK_OUTLINED,
        password=True,
        can_reveal_password=True,
    )

    api_key = _input_field(
        label="intervals.icu API key",
        value=existing_api_key,
        prefix_icon=ft.Icons.KEY_OUTLINED,
        password=True,
        can_reveal_password=True,
        helper="Settings → Developer on intervals.icu",
    )

    max_activities = _input_field(
        label="Activities to sync",
        value=str(config.max_activities),
        prefix_icon=ft.Icons.FORMAT_LIST_NUMBERED,
        keyboard_type=ft.KeyboardType.NUMBER,
        helper="Number of recent activities to sync on each run",
    )

    workout_days_ahead = _input_field(
        label="Workout upload window (days)",
        value=str(config.workout_days_ahead),
        prefix_icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
        keyboard_type=ft.KeyboardType.NUMBER,
        helper=(
            "Planned workouts from intervals.icu to upload to iGPSPORT and/or Bryton; "
            "1 = today only"
        ),
    )

    activity_type = ft.Dropdown(
        label="Activity type on intervals.icu",
        value=config.activity_type,
        border_radius=theme.RADIUS_SM,
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
        active_color=colors["accent"],
    )

    force_resync = ft.Switch(
        label="Force re-sync (re-download even if already uploaded)",
        value=config.force_resync,
        active_color=colors["accent"],
    )

    upload_dropbox = ft.Switch(
        label="Upload activities to Dropbox",
        value=(
            config.upload_dropbox
            and bool(existing_dropbox_token)
            and bool(dropbox_app_key)
        ),
        disabled=not bool(existing_dropbox_token and dropbox_app_key),
        active_color=colors["accent"],
    )
    dropbox_folder = _input_field(
        label="Dropbox folder",
        value=config.dropbox_folder or DEFAULT_DROPBOX_FOLDER,
        prefix_icon=ft.Icons.FOLDER_OUTLINED,
        helper="Dropbox path, e.g. /Fit files",
    )
    dropbox_date_filenames_switch = ft.Switch(
        label="Use date in Dropbox filenames",
        value=config.dropbox_date_filenames,
        active_color=colors["accent"],
    )
    dropbox_date_filenames = ft.Column(
        spacing=4,
        tight=True,
        controls=[
            dropbox_date_filenames_switch,
            ft.Text(
                "iGPSPORT: ride-0-YYYY-MM-DD-HH-MM-SS.fit · "
                "Bryton: YYMMDDHHMMSS.fit",
                size=12,
                color=colors["text_muted"],
            ),
        ],
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
        color=colors["text_muted"],
    )
    dropbox_auth_code = _input_field(
        label="Dropbox authorization code",
        prefix_icon=ft.Icons.KEY_OUTLINED,
        visible=False,
    )
    dropbox_finish_button = ft.OutlinedButton(
        "Finish connection",
        icon=ft.Icons.CHECK,
        visible=False,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_SM),
        ),
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
        icon=ft.Icons.CLOUD_UPLOAD_OUTLINED,
        disabled=not bool(dropbox_app_key),
        on_click=connect_dropbox,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_SM),
        ),
    )
    dropbox_disconnect_button = ft.TextButton(
        "Disconnect",
        icon=ft.Icons.LINK_OFF,
        disabled=not bool(existing_dropbox_token),
        on_click=disconnect_dropbox,
    )
    dropbox_finish_button.on_click = finish_dropbox

    dropbox_options = ft.ExpansionTile(
        title=ft.Text("Dropbox", weight=ft.FontWeight.W_500),
        subtitle=ft.Text(
            dropbox_status.value or "Optional cloud backup",
            size=12,
            color=colors["text_muted"],
        ),
        leading=ft.Icon(ft.Icons.CLOUD_OUTLINED, color=colors["accent"]),
        affinity=ft.TileAffinity.LEADING,
        expanded=config.upload_dropbox,
        controls=[
            ft.Container(
                padding=ft.Padding(theme.SPACE_MD, 0, theme.SPACE_MD, theme.SPACE_SM),
                content=ft.Column(
                    spacing=theme.SPACE_SM,
                    controls=[
                        dropbox_status,
                        ft.Row(
                            spacing=theme.SPACE_SM,
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

    profile_sync_status = ft.Text(
        "Checking…",
        size=12,
        color=colors["text_muted"],
        max_lines=2,
        no_wrap=False,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    profile_sync_hint = ft.Text(
        "Add iGPSPORT credentials and intervals.icu API key first.",
        size=12,
        color=colors["text_muted"],
        visible=False,
    )
    profile_sync_message_area = ft.Container(
        height=34,
        content=ft.Column(
            tight=True,
            spacing=0,
            controls=[profile_sync_status, profile_sync_hint],
        ),
        alignment=ft.Alignment.TOP_LEFT,
    )
    profile_sync_button = ft.OutlinedButton(
        "Sync profile now",
        icon=ft.Icons.SYNC,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_SM),
        ),
    )
    profile_sync_check_on_launch = ft.Switch(
        label="Check on app launch",
        value=config.profile_sync_check_on_launch,
        active_color=colors["accent"],
    )
    profile_sync_actions = ft.Row(
        spacing=theme.SPACE_MD,
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            profile_sync_button,
            profile_sync_check_on_launch,
        ],
    )

    async def refresh_profile_sync_status() -> None:
        creds = await profile_sync_ui.credentials_ready(config, store)
        if creds is None:
            profile_sync_status.visible = False
            profile_sync_hint.visible = True
            profile_sync_button.disabled = True
            page.update()
            return

        profile_sync_hint.visible = False
        profile_sync_status.visible = True
        profile_sync_button.disabled = False
        profile_sync_status.value = "Checking…"
        page.update()
        status = await profile_sync_ui.check_profile_thresholds(config, store)
        profile_sync_status.value = profile_sync_ui.format_threshold_status(status)
        page.update()

    async def on_profile_sync_click(_: ft.ControlEvent) -> None:
        profile_sync_button.disabled = True
        page.update()
        await profile_sync_ui.sync_with_feedback(page, config, store)
        await refresh_profile_sync_status()

    profile_sync_button.on_click = on_profile_sync_click

    async def on_profile_tile_change(e: ft.ControlEvent) -> None:
        if e.control.expanded:
            await refresh_profile_sync_status()

    profile_sync_options = ft.ExpansionTile(
        title=ft.Text("iGPSPORT profile", weight=ft.FontWeight.W_500),
        subtitle=ft.Text(
            "FTP, LTHR, max HR, and zones from intervals.icu",
            size=12,
            color=colors["text_muted"],
        ),
        leading=ft.Icon(ft.Icons.MONITOR_HEART_OUTLINED, color=colors["accent"]),
        affinity=ft.TileAffinity.LEADING,
        on_change=on_profile_tile_change,
        controls=[
            ft.Container(
                padding=ft.Padding(theme.SPACE_MD, 0, theme.SPACE_MD, theme.SPACE_SM),
                content=ft.Column(
                    tight=True,
                    spacing=theme.SPACE_XS,
                    controls=[
                        profile_sync_message_area,
                        profile_sync_actions,
                    ],
                ),
            )
        ],
    )

    save_to_downloads = ft.Switch(
        label="Save to phone's Downloads folder",
        value=config.save_to_downloads,
        active_color=colors["accent"],
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
        folder_detail = ft.Text(note, size=13, color=colors["text_muted"])
        folder_trailing: ft.Control | None = None
    else:
        folder_detail = ft.Text(
            config.download_dir, size=13, selectable=True, no_wrap=False
        )
        folder_trailing = ft.IconButton(
            ft.Icons.FOLDER_OPEN_OUTLINED,
            tooltip="Open folder",
            icon_color=colors["accent"],
            on_click=lambda _: open_folder(config.download_dir),
        )

    storage_inner_controls: list[ft.Control]
    if is_mobile:
        storage_inner_controls = [save_to_downloads, folder_detail]
    else:
        storage_inner_controls = [
            ft.Row(
                spacing=theme.SPACE_SM,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    ft.Column(
                        expand=True,
                        spacing=2,
                        controls=[
                            ft.Text(
                                "Download folder",
                                size=12,
                                weight=ft.FontWeight.W_500,
                                color=colors["text"],
                            ),
                            folder_detail,
                        ],
                    ),
                    *( [folder_trailing] if folder_trailing else [] ),
                ],
            )
        ]

    storage_options = ft.ExpansionTile(
        title=ft.Text("Storage", weight=ft.FontWeight.W_500),
        subtitle=ft.Text(
            (
                "Save to Downloads or app storage"
                if is_mobile
                else config.download_dir
            ),
            size=12,
            color=colors["text_muted"],
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
        leading=ft.Icon(ft.Icons.FOLDER_OUTLINED, color=colors["accent"]),
        affinity=ft.TileAffinity.LEADING,
        controls=[
            ft.Container(
                padding=ft.Padding(theme.SPACE_MD, 0, theme.SPACE_MD, theme.SPACE_SM),
                content=ft.Column(
                    spacing=theme.SPACE_SM,
                    controls=storage_inner_controls,
                ),
            )
        ],
    )

    igp_credentials = ft.Column(
        spacing=theme.SPACE_SM,
        controls=[igp_user, igp_password],
    )
    bryton_credentials = ft.Column(
        spacing=theme.SPACE_SM,
        controls=[bryton_user, bryton_password],
    )
    workout_sync_section = ft.Container(
        visible=config.enable_igpsport or config.enable_bryton,
        content=workout_days_ahead,
    )
    dropbox_section = ft.Container(
        visible=config.enable_igpsport or config.enable_bryton,
        content=dropbox_options,
    )
    profile_sync_section = ft.Container(
        visible=config.enable_igpsport,
        content=profile_sync_options,
    )

    def update_source_visibility(_: ft.ControlEvent | None = None) -> None:
        igp_credentials.visible = bool(enable_igpsport.value)
        workout_sync_section.visible = bool(enable_igpsport.value or enable_bryton.value)
        dropbox_section.visible = bool(enable_igpsport.value or enable_bryton.value)
        profile_sync_section.visible = bool(enable_igpsport.value)
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
        config.profile_sync_check_on_launch = bool(profile_sync_check_on_launch.value)
        config.activity_type = activity_type.value or ""
        config.dropbox_folder = dropbox_folder.value.strip() or DEFAULT_DROPBOX_FOLDER
        config.dropbox_date_filenames = bool(dropbox_date_filenames_switch.value)
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
        if on_profile_sync_check is not None and config.enable_igpsport:
            await on_profile_sync_check()

    save_button = ft.FilledButton(
        content=ft.Row(
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.SAVE_OUTLINED, size=20),
                ft.Text("Save settings", font_family=f"{theme.FONT_BODY}Medium"),
            ],
        ),
        on_click=save,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_SM),
            padding=ft.Padding(theme.SPACE_XL, theme.SPACE_MD, theme.SPACE_XL, theme.SPACE_MD),
        ),
    )

    return ft.Column(
        spacing=theme.SPACE_LG,
        controls=[
            ft.Column(
                spacing=theme.SPACE_SM,
                controls=[
                    theme.display_text("Settings", size=26, color=colors["text"]),
                    theme.muted_text(
                        "Credentials are stored in your operating system's secure vault, "
                        "never in a plain file.",
                        page,
                    ),
                ],
            ),
            theme.settings_section(
                page,
                "Accounts",
                api_key,
                enable_igpsport,
                igp_credentials,
                enable_bryton,
                bryton_credentials,
                subtitle="Enable sources and sign in to each service.",
            ),
            theme.settings_section(
                page,
                "Sync behavior",
                max_activities,
                activity_type,
                delete_after_upload,
                force_resync,
                workout_sync_section,
            ),
            profile_sync_section,
            dropbox_section,
            storage_options,
            save_button,
            ft.Container(height=theme.SPACE_MD),
        ],
    )
