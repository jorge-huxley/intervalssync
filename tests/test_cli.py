"""Tests for the headless CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from igpsync import cli, cli_config, cli_env, core


def _write_env(path: Path, **overrides: str) -> None:
    values = {
        cli_env.IGP_USER_KEY: "user@example.com",
        cli_env.IGP_PASSWORD_KEY: "secret",
        cli_env.INTERVALS_API_KEY_KEY: "api-key-123",
        **overrides,
    }
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_parse_dotenv_comments_and_quotes():
    text = """
# comment
IGPSYNC_IGP_USER="quoted@example.com"
export IGPSYNC_IGP_PASSWORD=pass
IGPSYNC_INTERVALS_API_KEY=key
"""
    parsed = cli_env.parse_dotenv(text)
    assert parsed["IGPSYNC_IGP_USER"] == "quoted@example.com"
    assert parsed["IGPSYNC_IGP_PASSWORD"] == "pass"
    assert parsed["IGPSYNC_INTERVALS_API_KEY"] == "key"


def test_load_credentials_missing_keys(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("IGPSYNC_IGP_USER=only-user\n", encoding="utf-8")

    with pytest.raises(cli_env.CliConfigError, match="IGPSYNC_IGP_PASSWORD"):
        cli_env.load_credentials(env_file)


def test_resolve_env_path_flag_wins(tmp_path: Path):
    custom = tmp_path / "custom.env"
    assert cli_env.resolve_env_path(env_file=custom) == custom


def test_resolve_env_path_uses_config_env_file(tmp_path: Path, monkeypatch):
    custom = tmp_path / "from-config.env"
    monkeypatch.delenv("HERMES_HOME", raising=False)
    assert cli_env.resolve_env_path(config_env_file=str(custom)) == custom


def test_resolve_env_path_uses_hermes_home(tmp_path: Path, monkeypatch):
    hermes_home = tmp_path / "profiles" / "coder"
    hermes_home.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    assert cli_env.resolve_env_path() == hermes_home / ".env"


def test_resolve_env_path_default_hermes(monkeypatch):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    assert cli_env.resolve_env_path() == Path.home() / ".hermes" / ".env"


def test_check_ok(tmp_path: Path, capsys):
    env_file = tmp_path / ".env"
    _write_env(env_file)

    args = cli._build_parser().parse_args(["check", "--env-file", str(env_file), "--json"])
    assert cli.cmd_check(args) == cli.EXIT_OK

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["env_file"] == str(env_file)


def test_check_missing_credentials(tmp_path: Path, capsys):
    env_file = tmp_path / ".env"
    env_file.write_text("IGPSYNC_IGP_USER=incomplete\n", encoding="utf-8")

    args = cli._build_parser().parse_args(["check", "--env-file", str(env_file), "--json"])
    assert cli.cmd_check(args) == cli.EXIT_CONFIG_ERROR

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "IGPSYNC_IGP_PASSWORD" in payload["error"]


def test_sync_json_success(tmp_path: Path, monkeypatch, capsys):
    env_file = tmp_path / ".env"
    _write_env(env_file)

    activities = [core.Activity(1, "Ride", "2026-06-15 08:00:00")]

    def fake_sync(config, progress=None):
        if progress:
            progress("working")
        return core.SyncResult(
            listed=1,
            downloaded=1,
            uploaded=1,
            activities=activities,
        )

    monkeypatch.setattr(cli, "sync", fake_sync)

    args = cli._build_parser().parse_args(
        ["sync", "--env-file", str(env_file), "--json", "--download-dir", str(tmp_path / "dl")]
    )
    assert cli.cmd_sync(args) == cli.EXIT_OK

    captured = capsys.readouterr()
    assert "working" in captured.err
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["uploaded"] == 1
    assert payload["activities"][0]["ride_id"] == 1


def test_sync_json_sync_error(tmp_path: Path, monkeypatch, capsys):
    env_file = tmp_path / ".env"
    _write_env(env_file)

    def fake_sync(config, progress=None):
        raise core.SyncError("login failed")

    monkeypatch.setattr(cli, "sync", fake_sync)

    args = cli._build_parser().parse_args(["sync", "--env-file", str(env_file), "--json"])
    assert cli.cmd_sync(args) == cli.EXIT_SYNC_ERROR

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "login failed"


def test_cli_config_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", tmp_path / "config.json")

    cfg = cli_config.CliConfig(env_file="/custom/.env", max_activities=10)
    cli_config.save(cfg)
    loaded = cli_config.load()
    assert loaded.env_file == "/custom/.env"
    assert loaded.max_activities == 10
