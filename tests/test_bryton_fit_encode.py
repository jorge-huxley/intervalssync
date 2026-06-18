"""Tests for Bryton-native FIT encoding from intervals.icu workout_doc."""

from __future__ import annotations

from garmin_fit_sdk import Decoder, Stream

from intervalssync.bryton.fit_encode import (
    BRYTON_FTP_OFFSET,
    TARGET_FTP,
    TARGET_LTHR,
    TARGET_MHR,
    icu_workout_doc_to_bryton_fit,
)


def _decode(fit_bytes: bytes) -> dict:
    messages, errors = Decoder(Stream.from_byte_array(fit_bytes)).read()
    assert not errors
    return messages


def test_encode_simple_ftp_step():
    doc = {
        "steps": [
            {
                "duration": 3600,
                "power": {"value": 100, "units": "%ftp"},
            }
        ],
    }
    fit_bytes = icu_workout_doc_to_bryton_fit("FTP Test", doc)
    assert fit_bytes is not None
    assert b".FIT" in fit_bytes[8:14]

    messages = _decode(fit_bytes)
    assert messages["workout_mesgs"][0]["wkt_name"] == "FTP Test"
    assert messages["file_id_mesgs"][0]["time_created"].tzinfo is not None
    assert messages["file_id_mesgs"][0]["manufacturer"] == "bryton"

    step = messages["workout_step_mesgs"][0]
    assert step["duration_type"] == "time"
    assert step["duration_value"] == 3600 * 1000
    assert step["duration_time"] == 3600.0
    assert step["target_type"] == TARGET_FTP
    assert step["custom_target_value_low"] == 100 + BRYTON_FTP_OFFSET
    assert step["custom_target_value_high"] == 100 + BRYTON_FTP_OFFSET


def test_encode_resolved_power_watts():
    doc = {
        "steps": [
            {
                "duration": 480,
                "warmup": True,
                "ramp": True,
                "power": {"start": 35, "end": 55, "units": "%ftp"},
                "_power": {"start": 127, "end": 135},
            }
        ],
    }
    fit_bytes = icu_workout_doc_to_bryton_fit("Warmup", doc)
    assert fit_bytes is not None
    step = _decode(fit_bytes)["workout_step_mesgs"][0]
    assert step["intensity"] == "warmup"
    assert step["target_type"] == TARGET_FTP
    assert step["custom_target_value_low"] == 35 + BRYTON_FTP_OFFSET
    assert step["custom_target_value_high"] == 55 + BRYTON_FTP_OFFSET


def test_encode_power_value_with_resolved_watts_range():
    doc = {
        "steps": [
            {
                "duration": 300,
                "power": {"value": 88, "units": "%ftp"},
                "_power": {"start": 200, "end": 220, "value": 210},
            }
        ],
    }
    fit_bytes = icu_workout_doc_to_bryton_fit("Interval", doc)
    assert fit_bytes is not None
    step = _decode(fit_bytes)["workout_step_mesgs"][0]
    assert step["target_type"] == TARGET_FTP
    assert step["custom_target_value_low"] == 84 + BRYTON_FTP_OFFSET
    assert step["custom_target_value_high"] == 92 + BRYTON_FTP_OFFSET


def test_encode_hr_steps_as_pct_mhr():
    doc = {
        "max_hr": 196,
        "target": "HR",
        "steps": [
            {
                "duration": 600,
                "hr": {"value": 1, "units": "hr_zone"},
                "_hr": {"start": 96.0, "end": 120.0},
            },
            {
                "reps": 10,
                "steps": [
                    {
                        "duration": 120,
                        "hr": {"value": 4, "units": "hr_zone"},
                        "_hr": {"start": 167.0, "end": 185.0},
                    },
                    {
                        "duration": 180,
                        "hr": {"value": 3, "units": "hr_zone"},
                        "_hr": {"start": 147.0, "end": 166.0},
                    },
                ],
            },
            {
                "duration": 600,
                "hr": {"value": 1, "units": "hr_zone"},
                "_hr": {"start": 96.0, "end": 120.0},
            },
        ],
    }
    fit_bytes = icu_workout_doc_to_bryton_fit("HR test", doc)
    assert fit_bytes is not None
    steps = _decode(fit_bytes)["workout_step_mesgs"]
    timed = [s for s in steps if s.get("duration_type") == "time"]
    assert len(timed) == 4
    assert timed[0]["target_type"] == TARGET_MHR
    assert timed[0]["custom_target_value_low"] == 49 + BRYTON_FTP_OFFSET
    assert timed[0]["custom_target_value_high"] == 61 + BRYTON_FTP_OFFSET
    assert timed[1]["custom_target_value_low"] == 85 + BRYTON_FTP_OFFSET
    assert timed[1]["custom_target_value_high"] == 94 + BRYTON_FTP_OFFSET
    assert timed[2]["custom_target_value_low"] == 75 + BRYTON_FTP_OFFSET
    assert timed[2]["custom_target_value_high"] == 85 + BRYTON_FTP_OFFSET
    assert timed[3]["custom_target_value_low"] == 49 + BRYTON_FTP_OFFSET
    assert timed[3]["custom_target_value_high"] == 61 + BRYTON_FTP_OFFSET


def test_encode_hr_steps_as_pct_lthr(monkeypatch):
    import intervalssync.bryton.fit_encode as fit_encode

    monkeypatch.setattr(fit_encode, "_BRYTON_HR_TARGET", "lthr")
    doc = {
        "lthr": 176,
        "target": "HR",
        "steps": [
            {
                "duration": 600,
                "hr": {"value": 1, "units": "hr_zone"},
                "_hr": {"start": 96.0, "end": 120.0},
            },
            {
                "reps": 10,
                "steps": [
                    {
                        "duration": 120,
                        "hr": {"value": 4, "units": "hr_zone"},
                        "_hr": {"start": 167.0, "end": 185.0},
                    },
                    {
                        "duration": 180,
                        "hr": {"value": 3, "units": "hr_zone"},
                        "_hr": {"start": 147.0, "end": 166.0},
                    },
                ],
            },
            {
                "duration": 600,
                "hr": {"value": 1, "units": "hr_zone"},
                "_hr": {"start": 96.0, "end": 120.0},
            },
        ],
    }
    fit_bytes = icu_workout_doc_to_bryton_fit("HR test", doc)
    assert fit_bytes is not None
    steps = _decode(fit_bytes)["workout_step_mesgs"]
    timed = [s for s in steps if s.get("duration_type") == "time"]
    assert len(timed) == 4
    assert timed[0]["target_type"] == TARGET_LTHR
    assert timed[0]["custom_target_value_low"] == 55 + BRYTON_FTP_OFFSET
    assert timed[0]["custom_target_value_high"] == 68 + BRYTON_FTP_OFFSET
    assert timed[1]["custom_target_value_low"] == 95 + BRYTON_FTP_OFFSET
    assert timed[1]["custom_target_value_high"] == 105 + BRYTON_FTP_OFFSET
    assert timed[2]["custom_target_value_low"] == 84 + BRYTON_FTP_OFFSET
    assert timed[2]["custom_target_value_high"] == 94 + BRYTON_FTP_OFFSET
    assert timed[3]["custom_target_value_low"] == 55 + BRYTON_FTP_OFFSET
    assert timed[3]["custom_target_value_high"] == 68 + BRYTON_FTP_OFFSET


def test_encode_interval_repeat_block():
    doc = {
        "steps": [
            {"duration": 900, "power": {"value": 55, "units": "%ftp"}, "warmup": True},
            {
                "reps": 3,
                "steps": [
                    {"duration": 480, "power": {"start": 88, "end": 94, "units": "%ftp"}},
                    {"duration": 300, "intensity": "recovery", "power": {"value": 55, "units": "%ftp"}},
                ],
            },
            {"duration": 600, "cooldown": True, "power": {"value": 50, "units": "%ftp"}},
        ],
    }
    fit_bytes = icu_workout_doc_to_bryton_fit("Sweet Spot", doc)
    assert fit_bytes is not None
    steps = _decode(fit_bytes)["workout_step_mesgs"]
    assert len(steps) == 5
    assert steps[0]["intensity"] == "warmup"
    assert steps[1]["wkt_step_name"] == "Work"
    assert steps[2]["wkt_step_name"] == "Recovery"
    repeat = steps[3]
    assert repeat["duration_type"] == "repeat_until_steps_cmplt"
    assert repeat["duration_value"] == 1
    assert repeat["repeat_steps"] == 3
    assert steps[4]["intensity"] == "cooldown"


def test_encode_returns_none_without_steps():
    assert icu_workout_doc_to_bryton_fit("Empty", {}) is None
    assert icu_workout_doc_to_bryton_fit("Empty", {"steps": []}) is None


def test_encode_long_workout_name():
    long_name = "HR test - this is a big title (8x5m) SS with efforts"
    doc = {
        "steps": [
            {
                "duration": 3600,
                "power": {"value": 100, "units": "%ftp"},
            }
        ],
    }
    fit_bytes = icu_workout_doc_to_bryton_fit(long_name, doc)
    assert fit_bytes is not None
    messages = _decode(fit_bytes)
    assert messages["workout_mesgs"][0]["wkt_name"] == long_name


def test_encode_power_zone_steps_from_resolved_watts():
    doc = {
        "ftp": 239,
        "lthr": 176,
        "target": "POWER",
        "steps": [
            {
                "duration": 600,
                "power": {"value": 2, "units": "power_zone", "target": "1s"},
                "_power": {"start": 132.0, "end": 179.0},
            },
            {
                "reps": 5,
                "steps": [
                    {
                        "duration": 60,
                        "power": {"value": 4, "units": "power_zone", "target": "1s"},
                        "_power": {"start": 216.0, "end": 250.0},
                    },
                    {
                        "duration": 120,
                        "power": {"value": 3, "units": "power_zone", "target": "1s"},
                        "_power": {"start": 180.0, "end": 215.0},
                    },
                ],
            },
        ],
    }
    fit_bytes = icu_workout_doc_to_bryton_fit("PWR test", doc)
    assert fit_bytes is not None
    steps = _decode(fit_bytes)["workout_step_mesgs"]
    timed = [s for s in steps if s.get("duration_type") == "time"]
    assert len(timed) == 3
    assert timed[0]["target_type"] == TARGET_FTP
    assert timed[0]["custom_target_value_low"] == 55 + BRYTON_FTP_OFFSET
    assert timed[0]["custom_target_value_high"] == 75 + BRYTON_FTP_OFFSET
    assert timed[1]["custom_target_value_low"] == 90 + BRYTON_FTP_OFFSET
    assert timed[1]["custom_target_value_high"] == 105 + BRYTON_FTP_OFFSET
    assert timed[2]["custom_target_value_low"] == 75 + BRYTON_FTP_OFFSET
    assert timed[2]["custom_target_value_high"] == 90 + BRYTON_FTP_OFFSET


def test_encode_open_duration_step():
    doc = {
        "steps": [
            {
                "until_lap_press": True,
                "intensity": "rest",
            }
        ],
    }
    fit_bytes = icu_workout_doc_to_bryton_fit("Open", doc)
    assert fit_bytes is not None
    step = _decode(fit_bytes)["workout_step_mesgs"][0]
    assert step["duration_type"] == "open"
    assert step["intensity"] == "rest"
