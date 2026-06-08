"""Settings view: enter credentials and have them saved to the OS vault."""

from __future__ import annotations

from typing import Awaitable, Callable

import flet as ft
from flet_permission_handler import Permission, PermissionHandler, PermissionStatus

from .. import config as config_module
from .. import secrets as secrets_module
from ..core import CYCLING_ACTIVITY_TYPES
from ..dropbox_client import (
    DEFAULT_DROPBOX_FOLDER,
    finish_dropbox_auth,
    get_dropbox_app_key,
    start_dropbox_auth,
)
from .system import open_folder


async def build_settings_view(
    page: ft.Page,
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
    on_saved: Callable[[], Awaitable[None]],
    perms: PermissionHandler | None = None,
    apply_download_location: Callable[[], Awaitable[None]] | None = None,
) -> ft.Control:
    """Return the settings card. `on_saved` is awaited after a successful save."""

    # Prefetch the currently-stored secrets to prefill the fields.
    existing_password = await store.get(secrets_module.IGP_PASSWORD) or ""
    existing_api_key = await store.get(secrets_module.INTERVALS_API_KEY) or ""
    existing_dropbox_token = await store.get(secrets_module.DROPBOX_REFRESH_TOKEN)
    dropbox_app_key = get_dropbox_app_key()

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

    # Android only: opt in to saving into the public Downloads folder (needs the
    # "all files access" permission, requested on save). Off = app-private.
    save_to_downloads = ft.Switch(
        label="Save to phone's Downloads folder",
        value=config.save_to_downloads,
    )

    # On desktop we show the path and an "open folder" button. On mobile the
    # text depends on whether files go to the (browsable) Downloads folder or to
    # app-private storage that no file manager can reach.
    if is_mobile:
        if config.save_to_downloads:
            note = "Saved to your phone's Downloads folder (Download/igpsport-fit)."
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
                # Requesting an already-granted permission just returns GRANTED.
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

        await store.set(secrets_module.IGP_PASSWORD, igp_password.value)
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
                    dropbox_options,
                    *([save_to_downloads] if is_mobile else []),
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
