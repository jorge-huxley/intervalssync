"""Sync view: one-click sync with a progress bar, live log and activity list."""

from __future__ import annotations

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
    log = ft.ListView(spacing=2, auto_scroll=True, height=260)

    sync_button = ft.FilledButton(
        "Sync activities",
        icon=ft.Icons.SYNC,
        height=52,
    )

    def append_log(message: str) -> None:
        log.controls.append(ft.Text(message, size=13, selectable=True))
        # Flush this single message to the UI immediately so the activity box
        # fills in step by step rather than all at once when the sync ends.
        page.update()

    def run_sync(igp_password: str, api_key: str | None) -> None:
        # Secrets are resolved on the async side and passed in, because the
        # secret store is async/page-bound and this runs on a worker thread.
        sync_config = SyncConfig(
            igp_user=config.igp_user,
            igp_password=igp_password,
            intervals_api_key=api_key,
            max_activities=config.max_activities,
            download_dir=config.download_dir,
            delete_after_upload=config.delete_after_upload,
            force_resync=config.force_resync,
            activity_type=config.activity_type,
            list_activities=config.step_list_activities,
            get_download_url=config.step_get_download_url,
            download_fit=config.step_download_fit,
            upload_intervals=config.step_upload_intervals,
        )

        try:
            result = sync(sync_config, progress=append_log)
            append_log(
                f"\nDone — uploaded {result.uploaded}, skipped {result.skipped}, "
                f"downloaded {result.downloaded}, failed {result.failed}."
            )
        except SyncError as exc:
            append_log(f"✗ {exc}")
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user
            append_log(f"✗ Unexpected error: {exc}")
        finally:
            progress.visible = False
            sync_button.disabled = False
            page.update()

    async def on_sync_click(_: ft.ControlEvent) -> None:
        igp_password = await store.get(secrets_module.IGP_PASSWORD)
        if not config.igp_user or not igp_password:
            page.show_dialog(ft.SnackBar(ft.Text("Add your credentials in Settings first.")))
            return
        api_key = await store.get(secrets_module.INTERVALS_API_KEY)

        log.controls.clear()
        progress.visible = True
        sync_button.disabled = True
        page.update()
        # Run off the UI thread (via Flet's managed executor) so the window
        # stays responsive and per-step updates flush to the client live.
        page.run_thread(run_sync, igp_password, api_key)

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
