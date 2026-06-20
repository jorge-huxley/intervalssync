"""Tests for sync milestone gamification logic."""

from __future__ import annotations

from intervalssync.gui import config as config_module
from intervalssync.gui import support_gamification as gamification


def test_rank_for_tiers():
    assert gamification.rank_for(0) == "Rookie"
    assert gamification.rank_for(1) == "Warm-up lap"
    assert gamification.rank_for(4) == "Warm-up lap"
    assert gamification.rank_for(5) == "Domestique"
    assert gamification.rank_for(10) == "Breakaway"
    assert gamification.rank_for(25) == "Climber"
    assert gamification.rank_for(50) == "Sprinter"
    assert gamification.rank_for(100) == "Century rider"
    assert gamification.rank_for(250) == "Grand tourer"
    assert gamification.rank_for(1000) == "Grand tourer"


def test_next_milestone_and_progress():
    assert gamification.next_milestone(0) == 1
    assert gamification.next_milestone(1) == 5
    assert gamification.next_milestone(9) == 10
    assert gamification.next_milestone(1000) is None

    assert gamification.progress_fraction(0) == 0.0
    assert gamification.progress_fraction(1) == 0.0
    assert gamification.progress_fraction(3) == 0.5
    assert gamification.progress_fraction(5) == 0.0
    assert gamification.progress_fraction(1000) == 1.0


def test_record_uploads_increments_and_saves(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    cfg = config_module.AppConfig(
        lifetime_activities_uploaded=1,
        celebrated_milestones=[1],
        stats_seeded=True,
    )
    assert gamification.record_uploads(cfg, activities=3) is None
    assert cfg.lifetime_activities_uploaded == 4
    assert config_module.total_uploads(cfg) == 4

    milestone = gamification.record_uploads(cfg, activities=1)
    assert milestone == 5
    assert cfg.lifetime_activities_uploaded == 5
    assert cfg.celebrated_milestones == [1, 5]

    assert gamification.record_uploads(cfg, workouts=1) is None
    assert cfg.lifetime_workouts_uploaded == 1
    assert config_module.total_uploads(cfg) == 6


def test_record_uploads_skips_zero_and_repeat_milestones(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    cfg = config_module.AppConfig(
        lifetime_activities_uploaded=9,
        celebrated_milestones=[1, 5],
        stats_seeded=True,
    )
    milestone = gamification.record_uploads(cfg, activities=1)
    assert milestone == 10
    assert cfg.celebrated_milestones == [1, 5, 10]

    assert gamification.record_uploads(cfg, activities=0) is None
    assert gamification.record_uploads(cfg, activities=1) is None


def test_record_uploads_returns_highest_crossed_milestone(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    cfg = config_module.AppConfig(stats_seeded=True)
    milestone = gamification.record_uploads(cfg, activities=10)
    assert milestone == 10
    assert cfg.lifetime_activities_uploaded == 10
    assert cfg.celebrated_milestones == [10]


def test_milestone_title():
    assert gamification.milestone_title(1) == "First transfer!"
    assert gamification.milestone_title(100) == "Century!"
    assert gamification.milestone_title(999) == "999 transfers!"
