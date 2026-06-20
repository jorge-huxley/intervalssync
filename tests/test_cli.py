"""Tests for the headless CLI."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

cli = importlib.import_module("intervalssync.cli.main")
from intervalssync.cli import config as cli_config
from intervalssync.cli import env as cli_env
from intervalssync.bryton import workout as bryton_workout
from intervalssync.bryton.exceptions import BrytonSyncError
from intervalssync.igpsport import core, workout


def _write_env(path: Path, **overrides: str) -> None:
    values = {
        cli_env.IGPSPORT_USER_KEY: "user@example.com",
        cli_env.IGPSPORT_PASSWORD_KEY: "secret",
        cli_env.INTERVALS_API_KEY_KEY: "api-key-123",
        **overrides,
    }
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def _write_bryton_env(path: Path, **overrides: str) -> None:
    values = {
        cli_env.BRYTON_EMAIL_KEY: "rider@example.com",
        cli_env.BRYTON_PASSWORD_KEY: "secret",
        cli_env.INTERVALS_API_KEY_KEY: "api-key-123",
        **overrides,
    }
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_parse_dotenv_comments_and_quotes():
    text = """
# comment
INTERVALSSYNC_IGPSPORT_USER="quoted@example.com"
export INTERVALSSYNC_IGPSPORT_PASSWORD=pass
INTERVALSSYNC_INTERVALS_API_KEY=key
"""
    parsed = cli_env.parse_dotenv(text)
    assert parsed["INTERVALSSYNC_IGPSPORT_USER"] == "quoted@example.com"
    assert parsed["INTERVALSSYNC_IGPSPORT_PASSWORD"] == "pass"
    assert parsed["INTERVALSSYNC_INTERVALS_API_KEY"] == "key"


def test_load_credentials_missing_keys(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("INTERVALSSYNC_IGPSPORT_USER=only-user\n", encoding="utf-8")

    with pytest.raises(cli_env.CliConfigError, match="INTERVALSSYNC_IGPSPORT_PASSWORD"):
        cli_env.load_credentials(env_file)


def test_load_credentials_missing_file_mentions_env_file(tmp_path: Path):
    env_file = tmp_path / "missing.env"

    with pytest.raises(cli_env.CliConfigError, match="--env-file") as exc_info:
        cli_env.load_credentials(env_file)

    assert "Secrets file not found" in str(exc_info.value)
    assert ".env.example" in str(exc_info.value)


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
    env_file.write_text("INTERVALSSYNC_IGPSPORT_USER=incomplete\n", encoding="utf-8")

    args = cli._build_parser().parse_args(["check", "--env-file", str(env_file), "--json"])
    assert cli.cmd_check(args) == cli.EXIT_CONFIG_ERROR

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "INTERVALSSYNC_IGPSPORT_PASSWORD" in payload["error"]


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

    monkeypatch.setattr(cli, "igpsport_sync", fake_sync)

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

    monkeypatch.setattr(cli, "igpsport_sync", fake_sync)

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


def test_upload_workouts_parser_accepts_flags():
    args = cli._build_parser().parse_args(
        ["upload-workouts", "--workout-days-ahead", "3", "--force-resync"]
    )
    assert args.command == "upload-workouts"
    assert args.workout_days_ahead == 3
    assert args.force_resync is True


def test_upload_workouts_json_success(tmp_path: Path, monkeypatch, capsys):
    env_file = tmp_path / ".env"
    _write_env(env_file)
    monkeypatch.setattr(cli_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", tmp_path / "config.json")

    def fake_upload(config, progress=None):
        if progress:
            progress("uploading")
        return workout.WorkoutUploadResult(
            listed=2,
            uploaded=1,
            skipped=1,
            uploaded_map={"42": 100},
        )

    monkeypatch.setattr(cli, "upload_workouts", fake_upload)

    args = cli._build_parser().parse_args(
        ["upload-workouts", "--env-file", str(env_file), "--json", "--workout-days-ahead", "2"]
    )
    assert cli.cmd_upload_workouts(args) == cli.EXIT_OK

    captured = capsys.readouterr()
    assert "uploading" in captured.err
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["source"] == "igpsport"
    assert payload["uploaded"] == 1
    assert payload["skipped"] == 1
    assert payload["no_steps"] == 0

    loaded = cli_config.load()
    assert loaded.uploaded_workouts == {"42": 100}
    assert loaded.workout_days_ahead == 1


def test_upload_workouts_json_sync_error(tmp_path: Path, monkeypatch, capsys):
    env_file = tmp_path / ".env"
    _write_env(env_file)

    def fake_upload(config, progress=None):
        raise core.SyncError("fetch failed")

    monkeypatch.setattr(cli, "upload_workouts", fake_upload)

    args = cli._build_parser().parse_args(
        ["upload-workouts", "--env-file", str(env_file), "--json"]
    )
    assert cli.cmd_upload_workouts(args) == cli.EXIT_SYNC_ERROR

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["source"] == "igpsport"
    assert payload["error"] == "fetch failed"


def test_upload_workouts_bryton_json_success(tmp_path: Path, monkeypatch, capsys):
    env_file = tmp_path / ".env"
    _write_bryton_env(env_file)
    monkeypatch.setattr(cli_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", tmp_path / "config.json")

    def fake_upload(config, progress=None):
        if progress:
            progress("uploading bryton")
        return bryton_workout.BrytonWorkoutUploadResult(
            listed=1,
            uploaded=1,
            uploaded_map={"99": "Morning_Ride"},
        )

    monkeypatch.setattr(cli, "bryton_upload_workouts", fake_upload)

    args = cli._build_parser().parse_args(
        [
            "upload-workouts",
            "--source",
            "bryton",
            "--env-file",
            str(env_file),
            "--json",
        ]
    )
    assert cli.cmd_upload_workouts(args) == cli.EXIT_OK

    captured = capsys.readouterr()
    assert "uploading bryton" in captured.err
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["source"] == "bryton"
    assert payload["uploaded"] == 1

    loaded = cli_config.load()
    assert loaded.uploaded_bryton_workouts == {"99": "Morning_Ride"}


def test_upload_workouts_bryton_json_sync_error(tmp_path: Path, monkeypatch, capsys):
    env_file = tmp_path / ".env"
    _write_bryton_env(env_file)

    def fake_upload(config, progress=None):
        raise BrytonSyncError("bryton fetch failed")

    monkeypatch.setattr(cli, "bryton_upload_workouts", fake_upload)

    args = cli._build_parser().parse_args(
        ["upload-workouts", "--source", "bryton", "--env-file", str(env_file), "--json"]
    )
    assert cli.cmd_upload_workouts(args) == cli.EXIT_SYNC_ERROR

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["source"] == "bryton"
    assert payload["error"] == "bryton fetch failed"


def test_sync_zones_parser_accepts_flags():
    args = cli._build_parser().parse_args(["sync-zones", "--sport", "Ride", "--json"])
    assert args.command == "sync-zones"
    assert args.sport == "Ride"
    assert args.json is True


def test_sync_zones_json_success(tmp_path: Path, monkeypatch, capsys):
    from intervalssync.igpsport import profile_sync as igp_profile_sync

    env_file = tmp_path / ".env"
    _write_env(env_file)

    def fake_sync(config, progress=None):
        if progress:
            progress("syncing zones")
        return igp_profile_sync.ProfileSyncResult(
            before={"member": {"ftp": 240, "mhr": 190, "lthr": 150}},
            after={
                "member": {"ftp": 242, "mhr": 193, "lthr": 176},
                "power": [{"start": 0, "end": 133}],
                "heartRate": [{"start": 0, "end": 120}],
            },
        )

    monkeypatch.setattr(cli, "sync_profile_zones", fake_sync)

    args = cli._build_parser().parse_args(
        ["sync-zones", "--env-file", str(env_file), "--json"]
    )
    assert cli.cmd_sync_zones(args) == cli.EXIT_OK

    captured = capsys.readouterr()
    assert "syncing zones" in captured.err
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["source"] == "igpsport"
    assert payload["ftp"] == 242
    assert payload["mhr"] == 193


def test_sync_zones_json_sync_error(tmp_path: Path, monkeypatch, capsys):
    env_file = tmp_path / ".env"
    _write_env(env_file)

    def fake_sync(config, progress=None):
        raise core.SyncError("profile update failed")

    monkeypatch.setattr(cli, "sync_profile_zones", fake_sync)

    args = cli._build_parser().parse_args(
        ["sync-zones", "--env-file", str(env_file), "--json"]
    )
    assert cli.cmd_sync_zones(args) == cli.EXIT_SYNC_ERROR

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "profile update failed"
