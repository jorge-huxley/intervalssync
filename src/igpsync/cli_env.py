"""Credential loading for the headless CLI.

All three credentials must live in a `.env` file. Do not use `hermes config set`
for the email or password — Hermes routes those to `config.yaml` in plaintext.
Append them to the profile `.env` instead (see docs/AGENT.md).
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
    "Ask the user to append all three keys to their Hermes profile .env "
    "(replace {profile_home} with the profile directory, e.g. "
    "~/.hermes/profiles/coach):\n"
    f"  echo '{IGP_USER_KEY}=<email>' >> {{profile_home}}/.env\n"
    f"  echo '{IGP_PASSWORD_KEY}=<password>' >> {{profile_home}}/.env\n"
    f"  echo '{INTERVALS_API_KEY_KEY}=<api-key>' >> {{profile_home}}/.env"
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
