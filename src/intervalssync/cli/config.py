"""Non-secret CLI settings persisted as JSON.

Secrets never live here — they are read from the Hermes profile .env file via
`env.py`.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_config_dir, user_downloads_dir

APP_NAME = "intervalssync-cli"

CONFIG_DIR = Path(user_config_dir(APP_NAME, appauthor=False))
CONFIG_PATH = CONFIG_DIR / "config.json"


def _default_download_dir() -> str:
    return str(Path(user_downloads_dir()) / "intervalssync-fit")


@dataclass
class CliConfig:
    # Optional override for the secrets .env file path.
    env_file: str = ""
    max_activities: int = 5
    download_dir: str = field(default_factory=_default_download_dir)
    delete_after_upload: bool = True
    force_resync: bool = False
    activity_type: str = ""
    # iGPSPORT ride id (decimal string) → intervals.icu activity id.
    uploaded_activities: dict[str, str] = field(default_factory=dict)
    # Planned workouts: intervals.icu event id → iGPSPORT workoutId.
    uploaded_workouts: dict[str, int] = field(default_factory=dict)
    # Per-event export fingerprints and verification state, bound to mapped IDs.
    # No workout content or provider identities are stored here.
    workout_export_state: dict[str, dict] = field(default_factory=dict)
    # Planned workouts: intervals.icu event id → Bryton FIT filename stem.
    uploaded_bryton_workouts: dict[str, str] = field(default_factory=dict)
    # How many calendar days of planned workouts to upload (1 = today only).
    workout_days_ahead: int = 1


def load() -> CliConfig:
    """Load CLI config from disk, falling back to defaults."""
    data: dict = {}
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    return CliConfig(
        **{k: v for k, v in data.items() if k in CliConfig.__annotations__}
    )


def save(config: CliConfig) -> None:
    """Atomically persist non-secret state without exposing a partial file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(config), indent=2)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{CONFIG_PATH.name}.", dir=CONFIG_DIR, text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(CONFIG_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)
