"""Credential loading for the headless CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ActivitySource = Literal["igpsport", "bryton"]

IGPSPORT_USER_KEY = "INTERVALSSYNC_IGPSPORT_USER"
IGPSPORT_PASSWORD_KEY = "INTERVALSSYNC_IGPSPORT_PASSWORD"
IGPSPORT_REGION_KEY = "INTERVALSSYNC_IGPSPORT_REGION"
BRYTON_EMAIL_KEY = "INTERVALSSYNC_BRYTON_EMAIL"
BRYTON_PASSWORD_KEY = "INTERVALSSYNC_BRYTON_PASSWORD"
INTERVALS_API_KEY_KEY = "INTERVALSSYNC_INTERVALS_API_KEY"

IGPSPORT_REQUIRED_KEYS = (
    IGPSPORT_USER_KEY,
    IGPSPORT_PASSWORD_KEY,
    INTERVALS_API_KEY_KEY,
)
BRYTON_REQUIRED_KEYS = (
    BRYTON_EMAIL_KEY,
    BRYTON_PASSWORD_KEY,
    INTERVALS_API_KEY_KEY,
)

_IGPSPORT_BODY = (
    f"  {IGPSPORT_USER_KEY}=<email>\n"
    f"  {IGPSPORT_PASSWORD_KEY}=<password>\n"
    f"  {INTERVALS_API_KEY_KEY}=<api-key>\n"
    f"  {IGPSPORT_REGION_KEY}=international  # or china for app.igpsport.cn"
)
_BRYTON_BODY = (
    f"  {BRYTON_EMAIL_KEY}=<email>\n"
    f"  {BRYTON_PASSWORD_KEY}=<password>\n"
    f"  {INTERVALS_API_KEY_KEY}=<api-key>"
)

ENV_OVERRIDE_HINT = (
    "Point intervalssync at a different file:\n"
    "  intervalssync <command> --env-file /path/to/.env\n"
    "You can also set env_file in the intervalssync-cli config.json."
)

SETUP_HINT_IGPSPORT = (
    "Add the required keys to your profile .env (see docs/AGENT.md):\n"
    f"  echo '{IGPSPORT_USER_KEY}=<email>' >> {{profile_home}}/.env\n"
    f"  echo '{IGPSPORT_PASSWORD_KEY}=<password>' >> {{profile_home}}/.env\n"
    f"  echo '{INTERVALS_API_KEY_KEY}=<api-key>' >> {{profile_home}}/.env"
)

SETUP_HINT_BRYTON = (
    "Add the required keys to your profile .env (see docs/AGENT.md):\n"
    f"  echo '{BRYTON_EMAIL_KEY}=<email>' >> {{profile_home}}/.env\n"
    f"  echo '{BRYTON_PASSWORD_KEY}=<password>' >> {{profile_home}}/.env\n"
    f"  echo '{INTERVALS_API_KEY_KEY}=<api-key>' >> {{profile_home}}/.env"
)


class CliConfigError(Exception):
    """Missing or invalid CLI credentials / env file."""


@dataclass(frozen=True)
class IgpsportCredentials:
    igp_user: str
    igp_password: str
    intervals_api_key: str
    igp_region: str = "international"


@dataclass(frozen=True)
class BrytonCredentials:
    bryton_email: str
    bryton_password: str
    intervals_api_key: str


def _default_hermes_env_path() -> Path:
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        return Path(hermes_home) / ".env"
    return Path.home() / ".hermes" / ".env"


def resolve_env_path(
    *,
    env_file: Path | None = None,
    config_env_file: str | None = None,
) -> Path:
    """Resolve the secrets .env path (first match wins)."""
    if env_file is not None:
        return env_file.expanduser()
    if config_env_file:
        return Path(config_env_file).expanduser()
    return _default_hermes_env_path()


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse KEY=value lines from a .env file (stdlib only)."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        values[key] = value
    return values


def _secrets_file_not_found_message(env_path: Path) -> str:
    return (
        f"Secrets file not found: {env_path}\n\n"
        f"Create that file with iGPSPORT keys:\n{_IGPSPORT_BODY}\n\n"
        f"or Bryton keys:\n{_BRYTON_BODY}\n\n"
        f"{ENV_OVERRIDE_HINT}\n\n"
        "For local development, copy .env.example to .env and pass --env-file .env."
    )


def _missing_keys_message(
    env_path: Path, missing: list[str], *, source: ActivitySource
) -> str:
    body = _IGPSPORT_BODY if source == "igpsport" else _BRYTON_BODY
    hint = SETUP_HINT_IGPSPORT if source == "igpsport" else SETUP_HINT_BRYTON
    return (
        f"Missing required keys in {env_path}: {', '.join(missing)}\n\n"
        f"Add them to the file:\n{body}\n\n{hint}"
    )


def load_igpsport_credentials(env_path: Path) -> IgpsportCredentials:
    if not env_path.is_file():
        raise CliConfigError(_secrets_file_not_found_message(env_path))

    values = parse_dotenv(env_path.read_text(encoding="utf-8"))
    missing = [key for key in IGPSPORT_REQUIRED_KEYS if not values.get(key)]
    if missing:
        raise CliConfigError(_missing_keys_message(env_path, missing, source="igpsport"))

    region = values.get(IGPSPORT_REGION_KEY, "international") or "international"
    if region not in ("international", "china"):
        raise CliConfigError(
            f"Invalid {IGPSPORT_REGION_KEY}={region!r} in {env_path} "
            "(expected 'international' or 'china')."
        )

    return IgpsportCredentials(
        igp_user=values[IGPSPORT_USER_KEY],
        igp_password=values[IGPSPORT_PASSWORD_KEY],
        intervals_api_key=values[INTERVALS_API_KEY_KEY],
        igp_region=region,
    )


def load_bryton_credentials(env_path: Path) -> BrytonCredentials:
    if not env_path.is_file():
        raise CliConfigError(_secrets_file_not_found_message(env_path))

    values = parse_dotenv(env_path.read_text(encoding="utf-8"))
    missing = [key for key in BRYTON_REQUIRED_KEYS if not values.get(key)]
    if missing:
        raise CliConfigError(_missing_keys_message(env_path, missing, source="bryton"))

    return BrytonCredentials(
        bryton_email=values[BRYTON_EMAIL_KEY],
        bryton_password=values[BRYTON_PASSWORD_KEY],
        intervals_api_key=values[INTERVALS_API_KEY_KEY],
    )


def load_credentials(env_path: Path, source: ActivitySource = "igpsport"):
    """Load credentials for the given activity source."""
    if source == "bryton":
        return load_bryton_credentials(env_path)
    return load_igpsport_credentials(env_path)
