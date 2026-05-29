"""Non-secret settings persisted as JSON in the per-user config directory.

Secrets never live here — they go to the OS vault via `secrets.py`. This file
holds the iGPSPORT username (an identifier, not a secret), the step toggles, the
activity cap and the download directory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_config_dir, user_downloads_dir

APP_NAME = "igpsport-intervals"

CONFIG_DIR = Path(user_config_dir(APP_NAME, appauthor=False))
CONFIG_PATH = CONFIG_DIR / "config.json"


def _default_download_dir() -> str:
    return str(Path(user_downloads_dir()) / "igpsport-fit")


@dataclass
class AppConfig:
    igp_user: str = ""
    max_activities: int = 5
    download_dir: str = field(default_factory=_default_download_dir)
    # Remove each .fit file once it has been uploaded to intervals.icu.
    delete_after_upload: bool = True
    # Re-download/re-upload activities even if they are already on intervals.icu.
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


def load() -> AppConfig:
    """Load config from disk, falling back to defaults."""
    data: dict = {}
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    return AppConfig(**{k: v for k, v in data.items() if k in AppConfig.__annotations__})


def save(config: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
