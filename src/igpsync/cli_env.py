"""Credential loading for the headless CLI.

Secrets are read from a .env file (Hermes profile or standalone). The CLI never
writes secrets — users set them via their agent profile, e.g.:

    {profile} config set IGPSYNC_IGP_USER you@example.com
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

IGP_USER_KEY = "IGPSYNC_IGP_USER"
IGP_PASSWORD_KEY = "IGPSYNC_IGP_PASSWORD"
INTERVALS_API_KEY_KEY = "IGPSYNC_INTERVALS_API_KEY"

REQUIRED_KEYS = (IGP_USER_KEY, IGP_PASSWORD_KEY, INTERVALS_API_KEY_KEY)

SETUP_HINT = (
    "Ask the user to set credentials once (replace {profile} with their "
    "Hermes profile name, or use 'hermes' for the default profile):\n"
    f"  {{profile}} config set {IGP_USER_KEY} <email>\n"
    f"  {{profile}} config set {IGP_PASSWORD_KEY} <password>\n"
    f"  {{profile}} config set {INTERVALS_API_KEY_KEY} <api-key>"
)


class CliConfigError(Exception):
    """Missing or invalid CLI credentials / env file."""


@dataclass(frozen=True)
class CliCredentials:
    igp_user: str
    igp_password: str
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


def load_credentials(env_path: Path) -> CliCredentials:
    """Load and validate the three required credentials from a .env file."""
    if not env_path.is_file():
        raise CliConfigError(
            f"Secrets file not found: {env_path}\n{SETUP_HINT}"
        )

    values = parse_dotenv(env_path.read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_KEYS if not values.get(key)]
    if missing:
        raise CliConfigError(
            f"Missing required keys in {env_path}: {', '.join(missing)}\n{SETUP_HINT}"
        )

    return CliCredentials(
        igp_user=values[IGP_USER_KEY],
        igp_password=values[IGP_PASSWORD_KEY],
        intervals_api_key=values[INTERVALS_API_KEY_KEY],
    )
