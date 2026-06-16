"""Non-secret CLI settings persisted as JSON.

Secrets never live here — they are read from the Hermes profile .env file via
`cli_env.py`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_config_dir, user_downloads_dir

APP_NAME = "igpsync-cli"

CONFIG_DIR = Path(user_config_dir(APP_NAME, appauthor=False))
CONFIG_PATH = CONFIG_DIR / "config.json"


def _default_download_dir() -> str:
    return str(Path(user_downloads_dir()) / "igpsport-fit")


@dataclass
class CliConfig:
    # Optional override for the secrets .env file path.
    env_file: str = ""
    max_activities: int = 5
    download_dir: str = field(default_factory=_default_download_dir)
    delete_after_upload: bool = True
    force_resync: bool = False
    activity_type: str = ""


def load() -> CliConfig:
    """Load CLI config from disk, falling back to defaults."""
    data: dict = {}
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    return CliConfig(**{k: v for k, v in data.items() if k in CliConfig.__annotations__})


def save(config: CliConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
