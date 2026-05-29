"""Sync view: one-click sync with a progress bar, live log and activity list."""

from __future__ import annotations

import threading

import flet as ft

from .. import config as config_module
from .. import secrets as secrets_module
from ..core import SyncConfig, SyncError, sync


def build_sync_view(
    page: ft.Page,
    config: config_module.AppConfig,
    store: secrets_module.SecretStore,
) -> ft.Control:
    progress = ft.ProgressBar(visible=False)
    log = ft.ListView(expand=True, spacing=2, auto_scroll=True, height=260)

    sync_button = ft.FilledButton(
        "Sync activities",
        icon=ft.Icons.SYNC,
        height=52,
    )

    def append_log(message: str) -> None:
        log.controls.append(ft.Text(message, size=13, selectable=True))
        page.update()

    def run_sync() -> None:
        store_pw = store.get(secrets_module.IGP_PASSWORD)
        api_key = store.get(secrets_module.INTERVALS_API_KEY)

        sync_config = SyncConfig(
            igp_user=config.igp_user,
            igp_password=store_pw or "",
            intervals_api_key=api_key,
            max_activities=config.max_activities,
            download_dir=config.download_dir,
            list_activities=config.step_list_activities,
            get_download_url=config.step_get_download_url,
            download_fit=config.step_download_fit,
            upload_intervals=config.step_upload_intervals,
        )

        try:
            result = sync(sync_config, progress=append_log)
            append_log(
                f"\nDone — downloaded {result.downloaded}, "
                f"uploaded {result.uploaded}, failed {result.failed}."
            )
        except SyncError as exc:
            append_log(f"✗ {exc}")
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user
            append_log(f"✗ Unexpected error: {exc}")
        finally:
            progress.visible = False
            sync_button.disabled = False
            page.update()

    def on_sync_click(_: ft.ControlEvent) -> None:
        if not config.igp_user or not store.get(secrets_module.IGP_PASSWORD):
            page.show_dialog(ft.SnackBar(ft.Text("Add your credentials in Settings first.")))
            return
        log.controls.clear()
        progress.visible = True
        sync_button.disabled = True
        page.update()
        # Run off the UI thread so the window stays responsive.
        threading.Thread(target=run_sync, daemon=True).start()

    sync_button.on_click = on_sync_click

    return ft.Column(
        spacing=16,
        controls=[
            ft.Text(
                "Download your latest rides from iGPSPORT and upload them to "
                "intervals.icu.",
                size=14,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            sync_button,
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
