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
from ..i18n import get_language, normalize_language, set_language, t
from . import theme
from . import profile_sync_ui
from .system import open_folder

# Survives Settings rebuild on language switch (Dropbox OAuth mid-flow).
_PAGE_DROPBOX_AUTH_ATTR = "_intervalssync_dropbox_auth_flow"
_PAGE_DROPBOX_CODE_ATTR = "_intervalssync_dropbox_auth_code"


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
    on_auto_sync_changed: Callable[[], Awaitable[None]] | None = None,
    on_language_changed: Callable[[], Awaitable[None]] | None = None,
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
        # Material TextField helpers default to one line and ellipsize on narrow screens.
        kwargs.setdefault("helper_max_lines", 4)
        # Fill the settings column width so attached helpers are not clipped early.
        kwargs.setdefault("width", float("inf"))
        if is_mobile:
            kwargs.setdefault("text_size", 14)
        return ft.TextField(**kwargs)

    def _dropdown(**kwargs: object) -> ft.Dropdown:
        kwargs.setdefault("border_radius", theme.RADIUS_SM)
        kwargs.setdefault("width", float("inf"))
        return ft.Dropdown(**kwargs)

    language_dropdown = _dropdown(
        label=t("settings.language.label"),
        value=normalize_language(config.language),
        options=[
            ft.dropdown.Option(key="en", text=t("settings.language.en")),
            ft.dropdown.Option(key="zh", text=t("settings.language.zh")),
        ],
    )

    enable_igpsport = ft.Switch(
        label=t("settings.enable.igpsport"),
        value=config.enable_igpsport,
        active_color=colors["accent"],
    )
    igp_region_value = (
        config.igp_region if config.igp_region in ("international", "china") else "international"
    )
    igp_region = _dropdown(
        label=t("settings.igp.region"),
        value=igp_region_value,
        options=[
            ft.dropdown.Option("international", t("settings.igp.region.international")),
            ft.dropdown.Option("china", t("settings.igp.region.china")),
        ],
        helper_text=t("settings.igp.region.helper"),
    )
    igp_user = _input_field(
        label=(
            t("settings.igp.user.phone")
            if igp_region_value == "china"
            else t("settings.igp.user.email")
        ),
        value=config.igp_user,
        prefix_icon=ft.Icons.PERSON_OUTLINED,
        autofocus=not config.igp_user,
    )
    igp_password = _input_field(
        label=t("settings.igp.password"),
        value=existing_igp_password,
        prefix_icon=ft.Icons.LOCK_OUTLINED,
        password=True,
        can_reveal_password=True,
    )

    enable_bryton = ft.Switch(
        label=t("settings.enable.bryton"),
        value=config.enable_bryton,
        active_color=colors["accent"],
    )
    bryton_user = _input_field(
        label=t("settings.bryton.email"),
        value=config.bryton_user,
        prefix_icon=ft.Icons.PERSON_OUTLINED,
    )
    bryton_password = _input_field(
        label=t("settings.bryton.password"),
        value=existing_bryton_password,
        prefix_icon=ft.Icons.LOCK_OUTLINED,
        password=True,
        can_reveal_password=True,
    )

    async def show_api_key_help(_: ft.ControlEvent) -> None:
        help_colors = theme.palette(page)
        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_MD),
                title=theme.display_text(t("settings.intervals.api_key.help.title"), size=20),
                content=ft.Column(
                    tight=True,
                    spacing=theme.SPACE_SM,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Text(
                            t("settings.intervals.api_key.help.step1"),
                            size=13,
                            color=help_colors["text"],
                            font_family=theme.body_font(),
                        ),
                        ft.Text(
                            t("settings.intervals.api_key.help.step2"),
                            size=13,
                            color=help_colors["text"],
                            font_family=theme.body_font(),
                        ),
                        ft.Text(
                            t("settings.intervals.api_key.help.step3"),
                            size=13,
                            color=help_colors["text"],
                            font_family=theme.body_font(),
                        ),
                        ft.Text(
                            t("settings.intervals.api_key.help.step4"),
                            size=13,
                            color=help_colors["text"],
                            font_family=theme.body_font(),
                        ),
                        ft.Text(
                            t("settings.intervals.api_key.help.step5"),
                            size=13,
                            color=help_colors["text"],
                            font_family=theme.body_font(),
                        ),
                        ft.Text(
                            t("settings.intervals.api_key.help.step6"),
                            size=13,
                            color=help_colors["text"],
                            font_family=theme.body_font(),
                        ),
                        ft.Text(
                            t("settings.intervals.api_key.help.step7"),
                            size=13,
                            color=help_colors["text"],
                            font_family=theme.body_font(),
                        ),
                        ft.Container(height=theme.SPACE_XS),
                        ft.Text(
                            t("settings.intervals.api_key.help.note"),
                            size=12,
                            color=help_colors["text_muted"],
                            font_family=theme.body_font(),
                        ),
                    ],
                ),
                actions=[
                    ft.FilledButton(
                        t("settings.intervals.api_key.help.close"),
                        on_click=lambda _: page.pop_dialog(),
                    ),
                ],
            )
        )
        page.update()

    api_key = _input_field(
        label=t("settings.intervals.api_key"),
        value=existing_api_key,
        prefix_icon=ft.Icons.KEY_OUTLINED,
        password=True,
        can_reveal_password=True,
        helper=t("settings.intervals.api_key.helper"),
        suffix=ft.IconButton(
            icon=ft.Icons.INFO_OUTLINE,
            icon_size=18,
            tooltip=t("settings.intervals.api_key.help.tooltip"),
            icon_color=colors["accent"],
            on_click=show_api_key_help,
        ),
    )

    max_activities = _input_field(
        label=t("settings.max_activities"),
        value=str(config.max_activities),
        prefix_icon=ft.Icons.FORMAT_LIST_NUMBERED,
        keyboard_type=ft.KeyboardType.NUMBER,
        helper=t("settings.max_activities.helper"),
    )

    workout_days_ahead = _input_field(
        label=t("settings.workout_days"),
        value=str(config.workout_days_ahead),
        prefix_icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
        keyboard_type=ft.KeyboardType.NUMBER,
        helper=t("settings.workout_days.helper"),
    )

    def _activity_type_option(key: str, label: str) -> ft.dropdown.Option:
        # Explicit Text so every row uses the same CJK face/size/weight.
        # Plain Option(text=...) mixes theme fonts and looks thick/thin.
        # Keep `text` for the closed-field label; `content` styles the menu rows.
        return ft.dropdown.Option(
            key=key,
            text=label,
            content=ft.Text(
                label,
                font_family=theme.body_font(),
                size=14,
                weight=ft.FontWeight.W_400,
            ),
        )

    activity_type = _dropdown(
        label=t("settings.activity_type"),
        value=config.activity_type,
        options=[
            _activity_type_option("", t("settings.activity_type.none")),
            *(
                _activity_type_option(value, t(f"settings.activity_type.{value}"))
                for value, _label in CYCLING_ACTIVITY_TYPES
            ),
        ],
    )

    delete_after_upload = ft.Switch(
        label=t("settings.delete_after_upload"),
        value=config.delete_after_upload,
        active_color=colors["accent"],
    )

    force_resync = ft.Switch(
        label=t("settings.force_resync"),
        value=config.force_resync,
        active_color=colors["accent"],
    )

    is_android = page.platform in (
        ft.PagePlatform.ANDROID,
        ft.PagePlatform.ANDROID_TV,
    )
    # TextField (not Dropdown) so helper_max_lines can wrap like other settings helpers.
    selected_auto_sync_minutes = config_module.clamp_auto_sync_interval(
        config.auto_sync_interval_minutes
    )

    def _auto_sync_interval_label(minutes: int) -> str:
        return t("settings.auto_sync.interval.value", minutes=minutes)

    auto_sync_enabled = ft.Switch(
        label=t("settings.auto_sync.enabled"),
        value=config.auto_sync_enabled,
        active_color=colors["accent"],
    )
    auto_sync_interval = _input_field(
        label=t("settings.auto_sync.interval"),
        value=_auto_sync_interval_label(selected_auto_sync_minutes),
        read_only=True,
        helper=(
            t("settings.auto_sync.helper.android")
            if is_android
            else t("settings.auto_sync.helper.desktop")
        ),
    )

    def _select_auto_sync_interval(minutes: int) -> None:
        nonlocal selected_auto_sync_minutes
        selected_auto_sync_minutes = minutes
        auto_sync_interval.value = _auto_sync_interval_label(minutes)
        page.update()

    auto_sync_interval.suffix = ft.PopupMenuButton(
        icon=ft.Icons.ARROW_DROP_DOWN,
        tooltip=t("settings.auto_sync.interval.tooltip"),
        items=[
            ft.PopupMenuItem(
                content=ft.Text(_auto_sync_interval_label(minutes)),
                on_click=lambda _e, m=minutes: _select_auto_sync_interval(m),
            )
            for minutes in config_module.AUTO_SYNC_INTERVALS
        ],
    )

    upload_dropbox = ft.Switch(
        label=t("settings.dropbox.upload"),
        value=(
            config.upload_dropbox
            and bool(existing_dropbox_token)
            and bool(dropbox_app_key)
        ),
        disabled=not bool(existing_dropbox_token and dropbox_app_key),
        active_color=colors["accent"],
    )
    dropbox_folder = _input_field(
        label=t("settings.dropbox.folder"),
        value=config.dropbox_folder or DEFAULT_DROPBOX_FOLDER,
        prefix_icon=ft.Icons.FOLDER_OUTLINED,
        helper=t("settings.dropbox.folder.helper"),
    )
    dropbox_date_filenames_switch = ft.Switch(
        label=t("settings.dropbox.date_filenames"),
        value=config.dropbox_date_filenames,
        active_color=colors["accent"],
    )
    dropbox_date_filenames = ft.Column(
        spacing=4,
        tight=True,
        controls=[
            dropbox_date_filenames_switch,
            ft.Text(
                t("settings.dropbox.filename_hint"),
                size=12,
                color=colors["text_muted"],
            ),
        ],
    )
    dropbox_status = ft.Text(
        (
            t("settings.dropbox.connected")
            if existing_dropbox_token and dropbox_app_key
            else t("settings.dropbox.no_app_key")
            if not dropbox_app_key
            else t("settings.dropbox.not_connected")
        ),
        size=13,
        color=colors["text_muted"],
    )
    dropbox_auth_code = _input_field(
        label=t("settings.dropbox.auth_code"),
        prefix_icon=ft.Icons.KEY_OUTLINED,
        visible=False,
    )
    dropbox_finish_button = ft.OutlinedButton(
        t("settings.dropbox.finish"),
        icon=ft.Icons.CHECK,
        visible=False,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_SM),
        ),
    )
    dropbox_auth_flow = getattr(page, _PAGE_DROPBOX_AUTH_ATTR, None)
    if dropbox_auth_flow is not None:
        dropbox_auth_code.visible = True
        dropbox_finish_button.visible = True
        dropbox_auth_code.value = getattr(page, _PAGE_DROPBOX_CODE_ATTR, "") or ""

    async def connect_dropbox(_: ft.ControlEvent) -> None:
        nonlocal dropbox_auth_flow
        if not dropbox_app_key:
            page.show_dialog(
                ft.SnackBar(ft.Text(t("settings.dropbox.snack.no_app_key")))
            )
            return
        dropbox_auth_flow, auth_url = start_dropbox_auth(dropbox_app_key)
        setattr(page, _PAGE_DROPBOX_AUTH_ATTR, dropbox_auth_flow)
        setattr(page, _PAGE_DROPBOX_CODE_ATTR, "")
        dropbox_auth_code.visible = True
        dropbox_finish_button.visible = True
        dropbox_auth_code.value = ""
        await page.launch_url(auth_url)
        page.show_dialog(
            ft.SnackBar(ft.Text(t("settings.dropbox.snack.paste_code")))
        )
        page.update()

    async def finish_dropbox(_: ft.ControlEvent) -> None:
        nonlocal dropbox_auth_flow
        if dropbox_auth_flow is None:
            page.show_dialog(ft.SnackBar(ft.Text(t("settings.dropbox.snack.start_first"))))
            return
        if not dropbox_auth_code.value:
            page.show_dialog(ft.SnackBar(ft.Text(t("settings.dropbox.snack.paste_first"))))
            return
        try:
            refresh_token = finish_dropbox_auth(
                dropbox_auth_flow, dropbox_auth_code.value
            )
        except Exception as exc:  # noqa: BLE001 — show auth failures directly
            page.show_dialog(ft.SnackBar(ft.Text(t("settings.dropbox.snack.failed", exc=exc))))
            return
        if not refresh_token:
            page.show_dialog(
                ft.SnackBar(ft.Text(t("settings.dropbox.snack.no_token")))
            )
            return
        await store.set(secrets_module.DROPBOX_REFRESH_TOKEN, refresh_token)
        dropbox_auth_flow = None
        setattr(page, _PAGE_DROPBOX_AUTH_ATTR, None)
        setattr(page, _PAGE_DROPBOX_CODE_ATTR, None)
        dropbox_auth_code.visible = False
        dropbox_finish_button.visible = False
        dropbox_status.value = t("settings.dropbox.connected")
        upload_dropbox.disabled = False
        upload_dropbox.value = True
        dropbox_disconnect_button.disabled = False
        page.show_dialog(ft.SnackBar(ft.Text(t("settings.dropbox.snack.connected"))))
        page.update()

    async def disconnect_dropbox(_: ft.ControlEvent) -> None:
        await store.delete(secrets_module.DROPBOX_REFRESH_TOKEN)
        config.upload_dropbox = False
        config_module.save(config)
        upload_dropbox.value = False
        upload_dropbox.disabled = True
        dropbox_status.value = t("settings.dropbox.not_connected")
        page.show_dialog(ft.SnackBar(ft.Text(t("settings.dropbox.snack.disconnected"))))
        page.update()

    dropbox_connect_button = ft.OutlinedButton(
        t("settings.dropbox.connect"),
        icon=ft.Icons.CLOUD_UPLOAD_OUTLINED,
        disabled=not bool(dropbox_app_key),
        on_click=connect_dropbox,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_SM),
        ),
    )
    dropbox_disconnect_button = ft.TextButton(
        t("settings.dropbox.disconnect"),
        icon=ft.Icons.LINK_OFF,
        disabled=not bool(existing_dropbox_token),
        on_click=disconnect_dropbox,
    )
    dropbox_finish_button.on_click = finish_dropbox

    dropbox_options = ft.ExpansionTile(
        title=ft.Text(t("settings.dropbox.title"), weight=ft.FontWeight.W_500),
        subtitle=ft.Text(
            dropbox_status.value or t("settings.dropbox.subtitle"),
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
        t("settings.profile.checking"),
        size=12,
        color=colors["text_muted"],
        max_lines=2,
        no_wrap=False,
        overflow=ft.TextOverflow.ELLIPSIS,
    )
    profile_sync_hint = ft.Text(
        t("settings.profile.hint.no_creds"),
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
        t("settings.profile.sync_now"),
        icon=ft.Icons.SYNC,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_SM),
        ),
    )
    profile_sync_check_on_launch = ft.Switch(
        label=t("settings.profile.check_on_launch"),
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
        profile_sync_status.value = t("settings.profile.checking")
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
        title=ft.Text(t("settings.profile.title"), weight=ft.FontWeight.W_500),
        subtitle=ft.Text(
            t("settings.profile.subtitle"),
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
        label=t("settings.storage.save_to_downloads"),
        value=config.save_to_downloads,
        active_color=colors["accent"],
    )

    if is_mobile:
        if config.save_to_downloads:
            note = t("settings.storage.note.downloads_on")
        else:
            note = t("settings.storage.note.downloads_off")
        folder_detail = ft.Text(note, size=13, color=colors["text_muted"])
        folder_trailing: ft.Control | None = None
    else:
        folder_detail = ft.Text(
            config.download_dir, size=13, selectable=True, no_wrap=False
        )
        folder_trailing = ft.IconButton(
            ft.Icons.FOLDER_OPEN_OUTLINED,
            tooltip=t("settings.storage.open_folder"),
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
                                t("settings.storage.download_folder"),
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
        title=ft.Text(t("settings.storage.title"), weight=ft.FontWeight.W_500),
        subtitle=ft.Text(
            (
                t("settings.storage.subtitle")
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
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[igp_region, igp_user, igp_password],
    )
    bryton_credentials = ft.Column(
        spacing=theme.SPACE_SM,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
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

    def update_igp_user_label(_: ft.ControlEvent | None = None) -> None:
        igp_user.label = (
            t("settings.igp.user.phone")
            if igp_region.value == "china"
            else t("settings.igp.user.email")
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
    igp_region.on_select = update_igp_user_label
    update_source_visibility()
    update_igp_user_label()

    async def _stash_form_before_language_change() -> None:
        """Persist in-progress edits so language rebuild does not wipe them."""
        nonlocal selected_auto_sync_minutes
        config.enable_igpsport = bool(enable_igpsport.value)
        config.enable_bryton = bool(enable_bryton.value)
        config.igp_user = (igp_user.value or "").strip()
        config.igp_region = igp_region.value or "international"
        config.bryton_user = (bryton_user.value or "").strip()
        try:
            config.max_activities = max(1, int(max_activities.value))
        except (TypeError, ValueError):
            pass
        try:
            config.workout_days_ahead = max(1, int(workout_days_ahead.value))
        except (TypeError, ValueError):
            pass
        config.delete_after_upload = bool(delete_after_upload.value)
        config.force_resync = bool(force_resync.value)
        config.profile_sync_check_on_launch = bool(profile_sync_check_on_launch.value)
        config.activity_type = activity_type.value or ""
        config.dropbox_folder = (dropbox_folder.value or "").strip() or DEFAULT_DROPBOX_FOLDER
        config.dropbox_date_filenames = bool(dropbox_date_filenames_switch.value)
        config.upload_dropbox = bool(upload_dropbox.value)
        config.auto_sync_enabled = bool(auto_sync_enabled.value)
        config.auto_sync_interval_minutes = config_module.clamp_auto_sync_interval(
            selected_auto_sync_minutes
        )
        if is_mobile:
            config.save_to_downloads = bool(save_to_downloads.value)
        if dropbox_auth_flow is not None:
            setattr(page, _PAGE_DROPBOX_AUTH_ATTR, dropbox_auth_flow)
            setattr(page, _PAGE_DROPBOX_CODE_ATTR, dropbox_auth_code.value or "")
        if igp_password.value:
            await store.set(secrets_module.IGP_PASSWORD, igp_password.value)
        if bryton_password.value:
            await store.set(secrets_module.BRYTON_PASSWORD, bryton_password.value)
        if api_key.value:
            await store.set(secrets_module.INTERVALS_API_KEY, api_key.value)

    async def apply_language_selection(e: ft.ControlEvent | None = None) -> None:
        # Flet 0.86 Dropdown fires on_select (not on_change). Prefer event data.
        raw = None
        if e is not None:
            raw = getattr(e, "data", None)
            if raw is None and getattr(e, "control", None) is not None:
                raw = e.control.value
        if raw is None:
            raw = language_dropdown.value
        new_lang = normalize_language(raw)
        if new_lang == get_language() and new_lang == normalize_language(config.language):
            return
        await _stash_form_before_language_change()
        config.language = new_lang
        set_language(new_lang)
        config_module.save(config)
        if on_language_changed is not None:
            await on_language_changed()

    language_dropdown.on_select = apply_language_selection

    async def save(_: ft.ControlEvent) -> None:
        if not enable_igpsport.value and not enable_bryton.value:
            page.show_dialog(
                ft.SnackBar(ft.Text(t("settings.save.error.no_source")))
            )
            return

        igp_pw = igp_password.value or existing_igp_password
        bryton_pw = bryton_password.value or existing_bryton_password

        if enable_igpsport.value:
            if not igp_user.value.strip():
                page.show_dialog(
                    ft.SnackBar(
                        ft.Text(t("settings.save.error.igp_user"))
                    )
                )
                return
            if not igp_pw:
                page.show_dialog(
                    ft.SnackBar(ft.Text(t("settings.save.error.igp_password")))
                )
                return

        if enable_bryton.value:
            if not bryton_user.value.strip():
                page.show_dialog(
                    ft.SnackBar(ft.Text(t("settings.save.error.bryton_email")))
                )
                return
            if not bryton_pw:
                page.show_dialog(
                    ft.SnackBar(ft.Text(t("settings.save.error.bryton_password")))
                )
                return

        config.language = normalize_language(language_dropdown.value)
        set_language(config.language)
        # Persist language even if later validation fails for other fields.
        config_module.save(config)
        config.enable_igpsport = bool(enable_igpsport.value)
        config.enable_bryton = bool(enable_bryton.value)
        config.igp_user = igp_user.value.strip()
        config.igp_region = igp_region.value or "international"
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

        want_auto_sync = bool(auto_sync_enabled.value)
        config.auto_sync_interval_minutes = config_module.clamp_auto_sync_interval(
            selected_auto_sync_minutes
        )
        auto_sync_interval.value = _auto_sync_interval_label(
            config.auto_sync_interval_minutes
        )

        message = t("settings.save.success.default")
        if want_auto_sync and is_android and perms is not None:
            notify_status = await perms.request(Permission.NOTIFICATION)
            battery_status = await perms.request(Permission.IGNORE_BATTERY_OPTIMIZATIONS)
            if notify_status != PermissionStatus.GRANTED:
                want_auto_sync = False
                auto_sync_enabled.value = False
                message = t("settings.save.success.no_notify_perm")
            elif battery_status != PermissionStatus.GRANTED:
                message = t("settings.save.success.battery_hint")
        config.auto_sync_enabled = want_auto_sync

        if config.upload_dropbox and not dropbox_app_key:
            config.upload_dropbox = False
            upload_dropbox.value = False
            message = t("settings.save.success.dropbox_no_key")
        elif config.upload_dropbox and not await store.get(
            secrets_module.DROPBOX_REFRESH_TOKEN
        ):
            config.upload_dropbox = False
            upload_dropbox.value = False
            message = t("settings.save.success.dropbox_not_connected")
        if is_mobile:
            want_downloads = bool(save_to_downloads.value)
            if want_downloads and perms is not None:
                status = await perms.request(Permission.MANAGE_EXTERNAL_STORAGE)
                if status != PermissionStatus.GRANTED:
                    want_downloads = False
                    save_to_downloads.value = False
                    message = t("settings.save.success.storage_denied")
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
        if on_auto_sync_changed is not None:
            await on_auto_sync_changed()
        if on_profile_sync_check is not None and config.enable_igpsport:
            await on_profile_sync_check()

    save_button = ft.FilledButton(
        content=ft.Row(
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.SAVE_OUTLINED, size=20),
                ft.Text(t("settings.save"), font_family=theme.body_font_medium()),
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
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Column(
                spacing=theme.SPACE_SM,
                controls=[
                    theme.display_text(t("settings.page.title"), size=26, color=colors["text"]),
                    theme.muted_text(t("settings.page.subtitle"), page),
                ],
            ),
            theme.settings_section(
                page,
                t("settings.section.language"),
                language_dropdown,
                subtitle=t("settings.section.language.subtitle"),
            ),
            theme.settings_section(
                page,
                t("settings.section.accounts"),
                api_key,
                enable_igpsport,
                igp_credentials,
                enable_bryton,
                bryton_credentials,
                subtitle=t("settings.section.accounts.subtitle"),
            ),
            theme.settings_section(
                page,
                t("settings.section.sync_behavior"),
                max_activities,
                activity_type,
                delete_after_upload,
                force_resync,
                auto_sync_enabled,
                auto_sync_interval,
                workout_sync_section,
            ),
            profile_sync_section,
            dropbox_section,
            storage_options,
            save_button,
            ft.Container(height=theme.SPACE_MD),
        ],
    )
