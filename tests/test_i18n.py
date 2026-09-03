"""Tests for bilingual i18n and support-entry language branching."""

from __future__ import annotations

from intervalssync import i18n
from intervalssync.gui import config as config_module
from intervalssync.gui import support_gamification as gamification


def test_normalize_and_detect_language():
    assert i18n.normalize_language("zh") == "zh"
    assert i18n.normalize_language("zh-CN") == "zh"
    assert i18n.normalize_language("zh_CN") == "zh"
    assert i18n.normalize_language("en-US") == "en"
    assert i18n.normalize_language(None) == "en"
    assert i18n.normalize_language("fr") == "en"


def test_t_switches_with_language():
    i18n.set_language("en")
    assert i18n.t("nav.sync") == "Sync"
    assert i18n.t("stats.kofi_button") == "Saved you time? Buy me a coffee"
    assert i18n.t("kofi.dialog.title") == "Support development"

    i18n.set_language("zh")
    assert i18n.t("nav.sync") == "同步"
    assert i18n.t("stats.kofi_button") == "了解耐力单车"
    assert i18n.t("kofi.dialog.title") == "耐力单车"
    assert i18n.t("partner.slogan") == "极致性价比的自行车功率训练营"
    assert "授权" in i18n.t("kofi.dialog.body")

    i18n.set_language("en")


def test_rank_and_milestone_follow_language():
    i18n.set_language("en")
    assert gamification.rank_for(0) == "Rookie"
    assert gamification.milestone_title(5) == "Domestique status!"

    i18n.set_language("zh")
    assert gamification.rank_for(0) == "新手"
    assert gamification.milestone_title(5) == "爬坡手达成！"

    i18n.set_language("en")


def test_is_chinese_for_partner_branch():
    i18n.set_language("en")
    assert not i18n.is_chinese()
    i18n.set_language("zh")
    assert i18n.is_chinese()
    i18n.set_language("en")


def test_config_persists_language(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)

    cfg = config_module.AppConfig(language="zh", stats_seeded=True)
    config_module.save(cfg)
    loaded = config_module.load()
    assert loaded.language == "zh"


def test_config_first_launch_detects_language_when_missing(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    monkeypatch.setattr(config_module, "detect_system_language", lambda: "zh")

    path.write_text("{}", encoding="utf-8")
    loaded = config_module.load()
    assert loaded.language == "zh"


def test_config_keeps_user_language_even_if_system_is_chinese(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_PATH", path)
    monkeypatch.setattr(config_module, "detect_system_language", lambda: "zh")

    path.write_text('{"language": "en", "stats_seeded": true}', encoding="utf-8")
    loaded = config_module.load()
    assert loaded.language == "en"


def test_progress_strings_localize():
    i18n.set_language("en")
    assert i18n.t("progress.login.igpsport") == "Logging in to iGPSPORT…"
    i18n.set_language("zh")
    assert i18n.t("progress.login.igpsport") == "正在登录 iGPSPORT…"
    i18n.set_language("en")


def test_kofi_url_unchanged():
    assert gamification.KOFI_URL == "https://ko-fi.com/jorge_huxley"
    assert gamification.PARTNER_LOGO == "endurance_logo.png"


def test_activity_type_label_and_user_errors():
    i18n.set_language("en")
    assert i18n.activity_type_label("MountainBikeRide") == "Mountain Bike Ride"
    assert i18n.localize_user_error("iGPSPORT credentials missing") == (
        "iGPSPORT credentials missing"
    )

    i18n.set_language("zh")
    assert i18n.activity_type_label("MountainBikeRide") == "山地骑行"
    assert i18n.localize_user_error("iGPSPORT credentials missing") == "缺少 iGPSPORT 凭据"
    assert i18n.localize_user_error("unknown boom") == "unknown boom"
    i18n.set_language("en")


def test_android_prop_language(tmp_path, monkeypatch):
    prop = tmp_path / "build.prop"
    prop.write_text("ro.product.locale=zh-CN\n", encoding="utf-8")
    monkeypatch.setattr(i18n, "_android_prop_language", lambda: "zh-CN")
    monkeypatch.setattr(i18n.sys, "platform", "linux")
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: (None, None))
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    assert i18n.detect_system_language() == "zh"
