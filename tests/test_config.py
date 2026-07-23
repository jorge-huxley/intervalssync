"""Tests for non-secret config persistence."""

from __future__ import annotations

import json

from intervalssync.gui import config as config_module


def test_defaults():
    cfg = config_module.AppConfig()
    assert cfg.enable_igpsport is True
    assert cfg.igp_region == "international"
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
    assert cfg.auto_sync_enabled is False
    assert cfg.auto_sync_interval_minutes == 60
    assert cfg.lifetime_activities_uploaded == 0
    assert cfg.lifetime_workouts_uploaded == 0
    assert cfg.celebrated_milestones == []
    assert cfg.stats_seeded is False
    assert config_module.total_uploads(cfg) == 0
    assert config_module.any_source_enabled(cfg) is True


def test_clamp_auto_sync_interval():
    assert config_module.clamp_auto_sync_interval(60) == 60
    assert config_module.clamp_auto_sync_interval(15) == 15
    assert config_module.clamp_auto_sync_interval(20) == 15
    assert config_module.clamp_auto_sync_interval(90) == 60
    assert config_module.clamp_auto_sync_interval(200) == 120
    assert config_module.clamp_auto_sync_interval("nope") == 60  # type: ignore[arg-type]


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


def test_load_seeds_workout_stats_from_maps(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "uploaded_workouts": {"evt1": 101, "evt2": 102},
                "uploaded_bryton_workouts": {"evt3": "file-a"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    loaded = config_module.load()
    assert loaded.lifetime_workouts_uploaded == 3
    assert loaded.lifetime_activities_uploaded == 0
    assert loaded.stats_seeded is True
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["lifetime_workouts_uploaded"] == 3
    assert saved["stats_seeded"] is True


def test_save_and_load_lifetime_stats(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    cfg = config_module.AppConfig(
        lifetime_activities_uploaded=42,
        lifetime_workouts_uploaded=8,
        celebrated_milestones=[1, 5, 10],
        stats_seeded=True,
    )
    config_module.save(cfg)

    loaded = config_module.load()
    assert loaded.lifetime_activities_uploaded == 42
    assert loaded.lifetime_workouts_uploaded == 8
    assert loaded.celebrated_milestones == [1, 5, 10]
    assert loaded.stats_seeded is True
    assert config_module.total_uploads(loaded) == 50


def test_save_and_load_igp_region(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    cfg = config_module.AppConfig(igp_user="13800000000", igp_region="china")
    config_module.save(cfg)

    loaded = config_module.load()
    assert loaded.igp_region == "china"
    assert loaded.igp_user == "13800000000"


def test_save_and_load_auto_sync(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    cfg = config_module.AppConfig(
        auto_sync_enabled=True,
        auto_sync_interval_minutes=30,
    )
    config_module.save(cfg)

    loaded = config_module.load()
    assert loaded.auto_sync_enabled is True
    assert loaded.auto_sync_interval_minutes == 30


def test_load_clamps_auto_sync_interval(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(
        '{"auto_sync_enabled": true, "auto_sync_interval_minutes": 17}',
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    loaded = config_module.load()
    assert loaded.auto_sync_enabled is True
    assert loaded.auto_sync_interval_minutes == 15
