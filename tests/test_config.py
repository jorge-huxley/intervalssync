"""Tests for non-secret config persistence."""

from __future__ import annotations

from igpsync import config as config_module


def test_defaults():
    cfg = config_module.AppConfig()
    assert cfg.delete_after_upload is True
    assert cfg.force_resync is False
    assert cfg.activity_type == ""  # "" = leave the uploaded sport untouched
    assert cfg.max_activities == 5
    assert cfg.upload_dropbox is False
    assert cfg.dropbox_folder == "/igpsport-fit"


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


def test_load_ignores_unknown_keys(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"igp_user": "x@y.com", "obsolete_key": 1}', encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    loaded = config_module.load()
    assert loaded.igp_user == "x@y.com"
    assert not hasattr(loaded, "obsolete_key")
