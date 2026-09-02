"""Optional periodic activity auto-sync with notifications."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import flet as ft

from . import config as config_module
from . import secrets as secrets_module
from . import support_gamification
from . import sync_runner

if TYPE_CHECKING:
    from flet_android_notifications import FletAndroidNotifications

_FGS_NOTIFICATION_ID = 1001
_UPLOAD_NOTIFICATION_ID = 1002
_CHANNEL_ID = "intervalssync_auto_sync"
_CHANNEL_NAME = "Auto-sync"
_CHANNEL_DESCRIPTION = "Background activity sync for Intervals Sync"
# Skip resume-triggered sync if a run finished within this many seconds.
_RESUME_MIN_GAP_SECONDS = 5 * 60


class AutoSyncController:
    """Starts/stops a periodic sync loop based on AppConfig.auto_sync_*."""

    def __init__(
        self,
        page: ft.Page,
        config: config_module.AppConfig,
        store: secrets_module.SecretStore,
        *,
        notifications: FletAndroidNotifications | None = None,
        is_android: bool = False,
    ) -> None:
        self._page = page
        self._config = config
        self._store = store
        self._notifications = notifications
        self._is_android = is_android
        self._generation = 0
        self._loop_task: asyncio.Task[None] | None = None
        self._fgs_active = False
        self._last_sync_finished_at = 0.0

    async def apply(self) -> None:
        """Start or stop the loop to match current config."""
        self._generation += 1
        generation = self._generation
        if self._loop_task is not None and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

        if not self._config.auto_sync_enabled:
            await self._stop_foreground_service()
            return

        interval = config_module.clamp_auto_sync_interval(
            self._config.auto_sync_interval_minutes
        )
        self._config.auto_sync_interval_minutes = interval
        await self._start_foreground_service()
        self._loop_task = asyncio.create_task(
            self._loop(generation, interval),
            name="intervalssync-auto-sync",
        )

    async def on_app_resume(self) -> None:
        """Run a sync soon after the app returns to the foreground."""
        if not self._config.auto_sync_enabled:
            return
        if time.monotonic() - self._last_sync_finished_at < _RESUME_MIN_GAP_SECONDS:
            return
        await self._run_once()

    async def _loop(self, generation: int, interval_minutes: int) -> None:
        try:
            await self._run_once()
            while generation == self._generation:
                await asyncio.sleep(interval_minutes * 60)
                if generation != self._generation:
                    break
                await self._run_once()
        except asyncio.CancelledError:
            raise

    async def _run_once(self) -> None:
        (
            igp_password,
            bryton_password,
            api_key,
            dropbox_refresh_token,
        ) = await sync_runner.load_sync_secrets(self._store)

        outcome = await asyncio.to_thread(
            sync_runner.run_enabled_activity_sync,
            self._config,
            igp_password=igp_password,
            bryton_password=bryton_password,
            api_key=api_key,
            dropbox_refresh_token=dropbox_refresh_token,
        )
        self._last_sync_finished_at = time.monotonic()
        if outcome.busy:
            return
        if outcome.uploaded <= 0:
            return

        support_gamification.record_uploads(
            self._config, activities=outcome.uploaded
        )
        await self._notify_uploads(outcome.uploaded)

    async def _notify_uploads(self, uploaded: int) -> None:
        ride_word = "ride" if uploaded == 1 else "rides"
        title = "Intervals Sync"
        body = f"Uploaded {uploaded} {ride_word} to intervals.icu"

        if self._is_android and self._notifications is not None:
            try:
                await self._notifications.show_notification(
                    notification_id=_UPLOAD_NOTIFICATION_ID,
                    title=title,
                    body=body,
                    channel_id=_CHANNEL_ID,
                    channel_name=_CHANNEL_NAME,
                    channel_description=_CHANNEL_DESCRIPTION,
                    importance="default",
                    play_sound=True,
                    enable_vibration=True,
                    auto_cancel=True,
                )
                return
            except Exception:  # noqa: BLE001 — fall back to in-app snack
                pass

        self._page.show_dialog(ft.SnackBar(ft.Text(body)))
        self._page.update()

    async def _start_foreground_service(self) -> None:
        if not self._is_android or self._notifications is None or self._fgs_active:
            return
        interval = self._config.auto_sync_interval_minutes
        try:
            await self._notifications.request_permissions()
            await self._notifications.start_foreground_service(
                notification_id=_FGS_NOTIFICATION_ID,
                title="Intervals Sync — auto-sync on",
                body=f"Checking for new rides every {interval} minutes",
                foreground_service_types=["special_use"],
                channel_id=_CHANNEL_ID,
                channel_name=_CHANNEL_NAME,
                channel_description=_CHANNEL_DESCRIPTION,
                importance="low",
                play_sound=False,
                enable_vibration=False,
                ongoing=True,
                silent=True,
                auto_cancel=False,
            )
            self._fgs_active = True
        except Exception:  # noqa: BLE001 — FGS is best-effort
            self._fgs_active = False

    async def _stop_foreground_service(self) -> None:
        if not self._is_android or self._notifications is None or not self._fgs_active:
            self._fgs_active = False
            return
        try:
            await self._notifications.stop_foreground_service()
        except Exception:  # noqa: BLE001 — ignore stop failures
            pass
        self._fgs_active = False
