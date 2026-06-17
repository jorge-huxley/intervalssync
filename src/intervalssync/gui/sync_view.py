"""Sync view: one-click sync with a progress bar, live log and activity list."""

from __future__ import annotations

from pathlib import Path

import flet as ft

from . import config as config_module
from . import secrets as secrets_module
from ..bryton.core import SyncConfig as BrytonSyncConfig, sync as bryton_sync
from ..bryton.exceptions import BrytonSyncError
from ..igpsport.core import SyncConfig as IgpSyncConfig, SyncError, sync as igpsport_sync
from ..dropbox_client import get_dropbox_app_key
from ..igpsport.workout import WorkoutUploadConfig, apply_uploaded_workout_map, upload_workouts


def build_sync_view(
    page: ft.Page,
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
) -> ft.Control:
    progress = ft.ProgressBar(visible=False)
    log = ft.ListView(spacing=2, auto_scroll=True, height=260)

    sync_igp_button = ft.FilledButton(
        "Sync iGPSPORT",
        icon=ft.Icons.SYNC,
        height=52,
        visible=config.enable_igpsport,
    )
    sync_bryton_button = ft.FilledButton(
        "Sync Bryton",
        icon=ft.Icons.SYNC,
        height=52,
        visible=config.enable_bryton,
    )
    upload_workouts_button = ft.OutlinedButton(
        "Upload workouts",
        icon=ft.Icons.FITNESS_CENTER,
        height=52,
        visible=config.enable_igpsport,
    )

    action_buttons = [
        btn
        for btn in (sync_igp_button, sync_bryton_button, upload_workouts_button)
        if btn.visible
    ]

    def set_buttons_enabled(enabled: bool) -> None:
        for button in action_buttons:
            button.disabled = not enabled

    def append_log(message: str) -> None:
        log.controls.append(ft.Text(message, size=13, selectable=True))
        page.update()

    def run_igpsport_sync(
        igp_password: str,
        api_key: str | None,
        dropbox_refresh_token: str | None,
        dropbox_app_key: str | None,
    ) -> None:
        sync_config = IgpSyncConfig(
            igp_user=config.igp_user,
            igp_password=igp_password,
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

        try:
            result = igpsport_sync(sync_config, progress=append_log)
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
            progress.visible = False
            set_buttons_enabled(True)
            page.update()

    def run_bryton_sync(bryton_password: str, api_key: str | None) -> None:
        sync_config = BrytonSyncConfig(
            bryton_email=config.bryton_user,
            bryton_password=bryton_password,
            intervals_api_key=api_key,
            max_activities=config.max_activities,
            download_dir=Path(config.download_dir),
            delete_after_upload=config.delete_after_upload,
            force_resync=config.force_resync,
            activity_type=config.activity_type,
            list_activities=config.step_list_activities,
            download_fit=config.step_download_fit,
            upload_intervals=config.step_upload_intervals,
        )

        try:
            result = bryton_sync(sync_config, progress=append_log)
            append_log(
                f"\nDone — uploaded {result.uploaded}, "
                f"downloaded {result.downloaded}, "
                f"skipped {result.skipped}, failed {result.failed}."
            )
        except BrytonSyncError as exc:
            append_log(f"✗ {exc}")
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user
            append_log(f"✗ Unexpected error: {exc}")
        finally:
            progress.visible = False
            set_buttons_enabled(True)
            page.update()

    def run_upload_workouts(igp_password: str, api_key: str) -> None:
        upload_config = WorkoutUploadConfig(
            igp_user=config.igp_user,
            igp_password=igp_password,
            intervals_api_key=api_key,
            workout_days_ahead=config.workout_days_ahead,
            uploaded_workouts=dict(config.uploaded_workouts),
            force_resync=config.force_resync,
        )

        try:
            result = upload_workouts(upload_config, progress=append_log)
            if result.uploaded_map or result.pruned_keys:
                apply_uploaded_workout_map(config.uploaded_workouts, result)
                config_module.save(config)
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

        log.controls.clear()
        progress.visible = True
        set_buttons_enabled(False)
        page.update()
        page.run_thread(run_bryton_sync, bryton_password, api_key)

    async def on_upload_workouts_click(_: ft.ControlEvent) -> None:
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
        page.run_thread(run_upload_workouts, igp_password, api_key)

    sync_igp_button.on_click = on_sync_igp_click
    sync_bryton_button.on_click = on_sync_bryton_click
    upload_workouts_button.on_click = on_upload_workouts_click

    return ft.Column(
        spacing=16,
        controls=[
            ft.Text(
                "Sync activities to intervals.icu from your enabled sources.",
                size=14,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Row(
                controls=action_buttons,
                spacing=12,
                wrap=True,
            ),
            progress,
            ft.Card(
                content=ft.Container(
                    padding=16,
                    content=ft.Column(
                        controls=[
                            ft.Text("Activity", size=16, weight=ft.FontWeight.BOLD),
                            log,
                        ],
                    ),
                )
            ),
        ],
    )
