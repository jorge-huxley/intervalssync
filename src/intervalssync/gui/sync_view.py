"""Sync view: one-click sync with a progress bar, live log and activity list."""

from __future__ import annotations

from pathlib import Path

import flet as ft

from . import config as config_module
from . import secrets as secrets_module
from ..bryton.core import SyncConfig as BrytonSyncConfig, sync as bryton_sync
from ..bryton.exceptions import BrytonSyncError
from ..bryton.workout import (
    BrytonWorkoutUploadConfig,
    apply_uploaded_bryton_workout_map,
    upload_workouts as bryton_upload_workouts,
)
from ..igpsport.core import SyncConfig as IgpSyncConfig, SyncError, sync as igpsport_sync
from ..dropbox_client import get_dropbox_app_key
from ..igpsport.workout import WorkoutUploadConfig, apply_uploaded_workout_map, upload_workouts
from . import support_gamification
from . import theme


def build_sync_view(
    page: ft.Page,
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
) -> ft.Control:
    colors = theme.palette(page)
    mobile = theme.is_mobile(page)
    progress = ft.ProgressBar(
        visible=False,
        color=colors["accent"],
        bgcolor=colors["surface_alt"],
        bar_height=3,
        border_radius=2,
    )
    log = ft.ListView(spacing=4, auto_scroll=True, height=280, expand=False)
    stats_refs = support_gamification.StatsCardRefs(
        headline=ft.Ref[ft.Text](),
        breakdown=ft.Ref[ft.Text](),
        progress_label=ft.Ref[ft.Text](),
        progress_bar=ft.Ref[ft.ProgressBar](),
    )
    stats_card = support_gamification.build_stats_card(page, config, stats_refs)

    def _action_button(label: str, icon: str, *, outlined: bool = False) -> ft.FilledButton | ft.OutlinedButton:
        label_size = 13 if mobile else 14
        content = ft.Row(
            spacing=theme.SPACE_XS,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Icon(icon, size=16 if mobile else 18),
                ft.Text(
                    label,
                    size=label_size,
                    font_family=f"{theme.FONT_BODY}Medium",
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=1,
                    expand=True,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
        )
        pad = theme.SPACE_SM if mobile else theme.SPACE_MD
        style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_SM),
            padding=ft.Padding(pad, theme.SPACE_SM, pad, theme.SPACE_SM),
        )
        if outlined:
            style = ft.ButtonStyle(
                shape=style.shape,
                padding=style.padding,
                side=ft.BorderSide(1, colors["border"]),
                color=colors["text"],
            )
            button: ft.FilledButton | ft.OutlinedButton = ft.OutlinedButton(content=content, style=style)
        else:
            button = ft.FilledButton(content=content, style=style)
        button.expand = True
        return button

    def _source_card(title: str, sync_btn: ft.Control, upload_btn: ft.Control) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                spacing=theme.SPACE_MD,
                controls=[
                    ft.Text(
                        title,
                        size=15,
                        weight=ft.FontWeight.W_600,
                        font_family=f"{theme.FONT_BODY}Medium",
                        color=colors["text"],
                    ),
                    ft.Column(
                        spacing=theme.SPACE_SM,
                        controls=[
                            ft.Row(spacing=0, controls=[sync_btn]),
                            ft.Row(spacing=0, controls=[upload_btn]),
                        ],
                    ),
                ],
            ),
            padding=theme.SPACE_LG,
            bgcolor=colors["surface"],
            border=ft.Border.all(1, colors["border"]),
            border_radius=theme.RADIUS_MD,
            expand=True,
        )

    sync_igp_button = _action_button("Sync activities", ft.Icons.SYNC)
    sync_bryton_button = _action_button("Sync activities", ft.Icons.SYNC)
    upload_igp_workouts_button = _action_button(
        "Upload workouts", ft.Icons.FITNESS_CENTER_OUTLINED, outlined=True
    )
    upload_bryton_workouts_button = _action_button(
        "Upload workouts", ft.Icons.FITNESS_CENTER_OUTLINED, outlined=True
    )

    action_cards: list[ft.Container] = []
    if config.enable_igpsport:
        action_cards.append(_source_card("iGPSPORT", sync_igp_button, upload_igp_workouts_button))
    if config.enable_bryton:
        action_cards.append(_source_card("Bryton", sync_bryton_button, upload_bryton_workouts_button))

    if len(action_cards) == 1:
        action_area = ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[ft.Container(content=action_cards[0], width=340)],
        )
    elif action_cards:
        if mobile:
            action_area = ft.Column(spacing=theme.SPACE_MD, controls=action_cards)
        else:
            action_area = ft.Row(spacing=theme.SPACE_MD, controls=action_cards)
    else:
        action_area = theme.muted_text("Enable a source in Settings to sync.", page)

    action_buttons: list[ft.FilledButton | ft.OutlinedButton] = []
    if config.enable_igpsport:
        action_buttons.extend([sync_igp_button, upload_igp_workouts_button])
    if config.enable_bryton:
        action_buttons.extend([sync_bryton_button, upload_bryton_workouts_button])

    def set_buttons_enabled(enabled: bool) -> None:
        for button in action_buttons:
            button.disabled = not enabled

    def append_log(message: str) -> None:
        line_color = colors["text"]
        if message.startswith("✗"):
            line_color = ft.Colors.RED_400
        elif message.startswith("\nDone"):
            line_color = colors["accent"]
        log.controls.append(
            ft.Text(
                message,
                size=12,
                selectable=True,
                font_family="Courier New",
                color=line_color,
            )
        )
        page.update()

    def _on_sync_complete(*, activities: int = 0, workouts: int = 0) -> None:
        milestone = support_gamification.record_uploads(
            config,
            activities=activities,
            workouts=workouts,
        )
        support_gamification.update_stats_display(page, config, stats_refs)
        if milestone is not None:

            async def _celebrate() -> None:
                await support_gamification.show_milestone_dialog(page, milestone)

            page.run_task(_celebrate)

    def run_igpsport_sync(
        igp_password: str,
        api_key: str | None,
        dropbox_refresh_token: str | None,
        dropbox_app_key: str | None,
    ) -> None:
        sync_config = IgpSyncConfig(
            igp_user=config.igp_user,
            igp_password=igp_password,
            igp_region=config.igp_region,
            intervals_api_key=api_key,
            dropbox_refresh_token=dropbox_refresh_token,
            dropbox_app_key=dropbox_app_key,
            max_activities=config.max_activities,
            download_dir=config.download_dir,
            delete_after_upload=config.delete_after_upload,
            force_resync=config.force_resync,
            activity_type=config.activity_type,
            list_activities=config.step_list_activities,
            get_download_url=config.step_get_download_url,
            download_fit=config.step_download_fit,
            upload_intervals=config.step_upload_intervals,
            upload_dropbox=config.upload_dropbox,
            dropbox_folder=config.dropbox_folder,
            dropbox_date_filenames=config.dropbox_date_filenames,
        )

        uploaded_count = 0
        try:
            result = igpsport_sync(sync_config, progress=append_log)
            uploaded_count = result.uploaded
            append_log(
                f"\nDone — intervals uploaded {result.uploaded}, "
                f"Dropbox uploaded {result.uploaded_dropbox}, "
                f"downloaded {result.downloaded}, "
                f"skipped {result.skipped}, Dropbox skipped {result.skipped_dropbox}, "
                f"failed {result.failed}, Dropbox failed {result.failed_dropbox}."
            )
        except SyncError as exc:
            append_log(f"✗ {exc}")
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user
            append_log(f"✗ Unexpected error: {exc}")
        finally:
            if uploaded_count > 0:
                _on_sync_complete(activities=uploaded_count)
            progress.visible = False
            set_buttons_enabled(True)
            page.update()

    def run_bryton_sync(
        bryton_password: str,
        api_key: str | None,
        dropbox_refresh_token: str | None,
        dropbox_app_key: str | None,
    ) -> None:
        sync_config = BrytonSyncConfig(
            bryton_email=config.bryton_user,
            bryton_password=bryton_password,
            intervals_api_key=api_key,
            dropbox_refresh_token=dropbox_refresh_token,
            dropbox_app_key=dropbox_app_key,
            max_activities=config.max_activities,
            download_dir=Path(config.download_dir),
            delete_after_upload=config.delete_after_upload,
            force_resync=config.force_resync,
            activity_type=config.activity_type,
            list_activities=config.step_list_activities,
            download_fit=config.step_download_fit,
            upload_intervals=config.step_upload_intervals,
            upload_dropbox=config.upload_dropbox,
            dropbox_folder=config.dropbox_folder,
            dropbox_date_filenames=config.dropbox_date_filenames,
        )

        uploaded_count = 0
        try:
            result = bryton_sync(sync_config, progress=append_log)
            uploaded_count = result.uploaded
            append_log(
                f"\nDone — intervals uploaded {result.uploaded}, "
                f"Dropbox uploaded {result.uploaded_dropbox}, "
                f"downloaded {result.downloaded}, "
                f"skipped {result.skipped}, Dropbox skipped {result.skipped_dropbox}, "
                f"failed {result.failed}, Dropbox failed {result.failed_dropbox}."
            )
        except BrytonSyncError as exc:
            append_log(f"✗ {exc}")
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user
            append_log(f"✗ Unexpected error: {exc}")
        finally:
            if uploaded_count > 0:
                _on_sync_complete(activities=uploaded_count)
            progress.visible = False
            set_buttons_enabled(True)
            page.update()

    def run_upload_igp_workouts(igp_password: str, api_key: str) -> None:
        upload_config = WorkoutUploadConfig(
            igp_user=config.igp_user,
            igp_password=igp_password,
            igp_region=config.igp_region,
            intervals_api_key=api_key,
            workout_days_ahead=config.workout_days_ahead,
            uploaded_workouts=dict(config.uploaded_workouts),
            force_resync=config.force_resync,
        )

        uploaded_count = 0
        try:
            result = upload_workouts(upload_config, progress=append_log)
            if result.uploaded_map or result.pruned_keys:
                apply_uploaded_workout_map(config.uploaded_workouts, result)
                config_module.save(config)
            uploaded_count = result.uploaded
            append_log(
                f"\nDone — uploaded {result.uploaded}, "
                f"skipped {result.skipped}, no steps {result.no_steps}, "
                f"failed {result.failed}."
            )
        except SyncError as exc:
            append_log(f"✗ {exc}")
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user
            append_log(f"✗ Unexpected error: {exc}")
        finally:
            if uploaded_count > 0:
                _on_sync_complete(workouts=uploaded_count)
            progress.visible = False
            set_buttons_enabled(True)
            page.update()

    def run_upload_bryton_workouts(bryton_password: str, api_key: str) -> None:
        upload_config = BrytonWorkoutUploadConfig(
            bryton_email=config.bryton_user,
            bryton_password=bryton_password,
            intervals_api_key=api_key,
            workout_days_ahead=config.workout_days_ahead,
            uploaded_workouts=dict(config.uploaded_bryton_workouts),
            force_resync=config.force_resync,
        )

        uploaded_count = 0
        try:
            result = bryton_upload_workouts(upload_config, progress=append_log)
            if result.uploaded_map or result.pruned_keys:
                apply_uploaded_bryton_workout_map(config.uploaded_bryton_workouts, result)
                config_module.save(config)
            uploaded_count = result.uploaded
            append_log(
                f"\nDone — uploaded {result.uploaded}, "
                f"skipped {result.skipped}, no steps {result.no_steps}, "
                f"failed {result.failed}."
            )
        except BrytonSyncError as exc:
            append_log(f"✗ {exc}")
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user
            append_log(f"✗ Unexpected error: {exc}")
        finally:
            if uploaded_count > 0:
                _on_sync_complete(workouts=uploaded_count)
            progress.visible = False
            set_buttons_enabled(True)
            page.update()

    async def on_sync_igp_click(_: ft.ControlEvent) -> None:
        igp_password = await store.get(secrets_module.IGP_PASSWORD)
        if not config.igp_user or not igp_password:
            page.show_dialog(ft.SnackBar(ft.Text("Add your iGPSPORT credentials in Settings first.")))
            return
        api_key = await store.get(secrets_module.INTERVALS_API_KEY)
        dropbox_refresh_token = await store.get(secrets_module.DROPBOX_REFRESH_TOKEN)
        dropbox_app_key = get_dropbox_app_key()

        log.controls.clear()
        progress.visible = True
        set_buttons_enabled(False)
        page.update()
        page.run_thread(
            run_igpsport_sync,
            igp_password,
            api_key,
            dropbox_refresh_token,
            dropbox_app_key,
        )

    async def on_sync_bryton_click(_: ft.ControlEvent) -> None:
        bryton_password = await store.get(secrets_module.BRYTON_PASSWORD)
        if not config.bryton_user or not bryton_password:
            page.show_dialog(ft.SnackBar(ft.Text("Add your Bryton credentials in Settings first.")))
            return
        api_key = await store.get(secrets_module.INTERVALS_API_KEY)
        dropbox_refresh_token = await store.get(secrets_module.DROPBOX_REFRESH_TOKEN)
        dropbox_app_key = get_dropbox_app_key()

        log.controls.clear()
        progress.visible = True
        set_buttons_enabled(False)
        page.update()
        page.run_thread(
            run_bryton_sync,
            bryton_password,
            api_key,
            dropbox_refresh_token,
            dropbox_app_key,
        )

    async def on_upload_igp_workouts_click(_: ft.ControlEvent) -> None:
        igp_password = await store.get(secrets_module.IGP_PASSWORD)
        if not config.igp_user or not igp_password:
            page.show_dialog(ft.SnackBar(ft.Text("Add your iGPSPORT credentials in Settings first.")))
            return
        api_key = await store.get(secrets_module.INTERVALS_API_KEY)
        if not api_key:
            page.show_dialog(
                ft.SnackBar(ft.Text("Add your intervals.icu API key in Settings first."))
            )
            return

        log.controls.clear()
        progress.visible = True
        set_buttons_enabled(False)
        page.update()
        page.run_thread(run_upload_igp_workouts, igp_password, api_key)

    async def on_upload_bryton_workouts_click(_: ft.ControlEvent) -> None:
        bryton_password = await store.get(secrets_module.BRYTON_PASSWORD)
        if not config.bryton_user or not bryton_password:
            page.show_dialog(ft.SnackBar(ft.Text("Add your Bryton credentials in Settings first.")))
            return
        api_key = await store.get(secrets_module.INTERVALS_API_KEY)
        if not api_key:
            page.show_dialog(
                ft.SnackBar(ft.Text("Add your intervals.icu API key in Settings first."))
            )
            return

        log.controls.clear()
        progress.visible = True
        set_buttons_enabled(False)
        page.update()
        page.run_thread(run_upload_bryton_workouts, bryton_password, api_key)

    sync_igp_button.on_click = on_sync_igp_click
    sync_bryton_button.on_click = on_sync_bryton_click
    upload_igp_workouts_button.on_click = on_upload_igp_workouts_click
    upload_bryton_workouts_button.on_click = on_upload_bryton_workouts_click

    log_panel = ft.Container(
        content=ft.Column(
            spacing=theme.SPACE_SM,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        theme.section_label("Activity log", page),
                        ft.Text(
                            "live",
                            size=10,
                            color=colors["accent"],
                            font_family=f"{theme.FONT_BODY}Medium",
                        ),
                    ],
                ),
                ft.Container(
                    content=log,
                    expand=True,
                    padding=theme.SPACE_MD,
                    bgcolor=colors["surface_alt"],
                    border_radius=theme.RADIUS_SM,
                    border=ft.Border(left=ft.BorderSide(3, colors["accent"])),
                ),
            ],
        ),
        padding=theme.SPACE_LG,
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=theme.RADIUS_MD,
    )

    return ft.Column(
        spacing=theme.SPACE_LG,
        controls=[
            ft.Column(
                spacing=theme.SPACE_SM,
                controls=[
                    theme.display_text("Your rides, synced", size=26, color=colors["text"]),
                    theme.muted_text(
                        "Pull recent activities from iGPSPORT or Bryton into intervals.icu, "
                        "or push planned workouts the other way.",
                        page,
                    ),
                ],
            ),
            action_area,
            progress,
            log_panel,
            stats_card,
            *(
                [support_gamification.build_dev_milestone_panel(page, config, stats_refs)]
                if support_gamification.dev_mode_enabled()
                else []
            ),
            ft.Container(height=theme.SPACE_MD),
        ],
    )
