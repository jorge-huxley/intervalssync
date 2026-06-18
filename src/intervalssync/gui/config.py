"""Non-secret settings persisted as JSON in the per-user config directory.

Secrets never live here — they go to the OS vault via `secrets.py`. This file
holds source usernames (identifiers, not secrets), step toggles, the activity
cap and the download directory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_config_dir, user_downloads_dir

APP_NAME = "intervalssync"

CONFIG_DIR = Path(user_config_dir(APP_NAME, appauthor=False))
CONFIG_PATH = CONFIG_DIR / "config.json"


def _default_download_dir() -> str:
    return str(Path(user_downloads_dir()) / "intervalssync-fit")


@dataclass
class AppConfig:
    enable_igpsport: bool = True
    enable_bryton: bool = False
    igp_user: str = ""
    bryton_user: str = ""
    max_activities: int = 5
    download_dir: str = field(default_factory=_default_download_dir)
    # Remove each .fit file once it has been uploaded to intervals.icu.
    delete_after_upload: bool = True
    # Re-download/re-upload activities even if already on intervals.icu or Dropbox.
    force_resync: bool = False
    # intervals.icu sport set on uploaded activities ("" = leave as uploaded).
    activity_type: str = ""
    # Android only: save downloads to the public Downloads folder (needs the
    # "all files access" permission) instead of app-private storage.
    save_to_downloads: bool = False
    # Step toggles (advanced). The GUI's one-click sync sets these for the user.
    step_list_activities: bool = True
    step_get_download_url: bool = True
    step_download_fit: bool = True
    step_upload_intervals: bool = True
    # Optional secondary upload target. Off by default because most users only
    # want intervals.icu.
    upload_dropbox: bool = False
    dropbox_folder: str = "/intervalssync-fit"
    dropbox_date_filenames: bool = True
    # Planned workouts: intervals.icu event id → iGPSPORT workoutId.
    uploaded_workouts: dict[str, int] = field(default_factory=dict)
    # Planned workouts: intervals.icu event id → Bryton file id or filename stem.
    uploaded_bryton_workouts: dict[str, str] = field(default_factory=dict)
    # How many calendar days of planned workouts to upload (1 = today only).
    workout_days_ahead: int = 1


def any_source_enabled(config: AppConfig) -> bool:
    return config.enable_igpsport or config.enable_bryton


def load() -> AppConfig:
    """Load config from disk, falling back to defaults."""
    data: dict = {}
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    # Migrate legacy single-source picker (ignored on save going forward).
    activity_source = data.pop("activity_source", None)
    cfg = AppConfig(**{k: v for k, v in data.items() if k in AppConfig.__annotations__})
    if activity_source == "bryton":
        cfg.enable_bryton = True
        cfg.enable_igpsport = False
    return cfg


def save(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
