"""Tests for non-secret config persistence."""

from __future__ import annotations

import json

from intervalssync.gui import config as config_module


def test_defaults():
    cfg = config_module.AppConfig()
    assert cfg.enable_igpsport is True
    assert cfg.enable_bryton is False
    assert cfg.delete_after_upload is True
    assert cfg.force_resync is False
    assert cfg.activity_type == ""  # "" = leave the uploaded sport untouched
    assert cfg.max_activities == 5
    assert cfg.upload_dropbox is False
    assert cfg.dropbox_folder == "/intervalssync-fit"
    assert cfg.dropbox_date_filenames is True
    assert cfg.uploaded_workouts == {}
    assert cfg.uploaded_bryton_workouts == {}
    assert cfg.workout_days_ahead == 1
    assert config_module.any_source_enabled(cfg) is True


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    # Redirect the config file into a temp dir so the real one is untouched.
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    cfg = config_module.AppConfig(
        igp_user="me@example.com",
        max_activities=3,
        activity_type="GravelRide",
        delete_after_upload=False,
        upload_dropbox=True,
        dropbox_folder="/rides",
        dropbox_date_filenames=False,
    )
    config_module.save(cfg)
    assert path.exists()

    loaded = config_module.load()
    assert loaded.igp_user == "me@example.com"
    assert loaded.max_activities == 3
    assert loaded.activity_type == "GravelRide"
    assert loaded.delete_after_upload is False
    assert loaded.upload_dropbox is True
    assert loaded.dropbox_folder == "/rides"
    assert loaded.dropbox_date_filenames is False


def test_load_ignores_unknown_keys(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"igp_user": "x@y.com", "obsolete_key": 1}', encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    loaded = config_module.load()
    assert loaded.igp_user == "x@y.com"
    assert not hasattr(loaded, "obsolete_key")


def test_save_and_load_bryton_flags(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    cfg = config_module.AppConfig(
        enable_igpsport=False,
        enable_bryton=True,
        bryton_user="rider@example.com",
    )
    config_module.save(cfg)

    loaded = config_module.load()
    assert loaded.enable_igpsport is False
    assert loaded.enable_bryton is True
    assert loaded.bryton_user == "rider@example.com"
    assert "activity_source" not in json.loads(path.read_text(encoding="utf-8"))


def test_load_migrates_activity_source_bryton(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        '{"activity_source": "bryton", "bryton_user": "a@b.com"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    loaded = config_module.load()
    assert loaded.enable_bryton is True
    assert loaded.enable_igpsport is False
    assert loaded.bryton_user == "a@b.com"


def test_load_migrates_activity_source_igpsport(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"activity_source": "igpsport", "igp_user": "u@x.com"}', encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    loaded = config_module.load()
    assert loaded.enable_igpsport is True
    assert loaded.enable_bryton is False
    assert loaded.igp_user == "u@x.com"
