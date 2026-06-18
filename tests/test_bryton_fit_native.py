"""Compare our Bryton FIT encoding to native reference files."""

from __future__ import annotations

from pathlib import Path

from garmin_fit_sdk import Decoder, Stream

from intervalssync.bryton.fit_encode import icu_workout_doc_to_bryton_fit

FIXTURES = Path(__file__).parent / "fixtures" / "bryton_workouts"


def _decode(path: Path) -> list[dict]:
    data = path.read_bytes()
    messages, errors = Decoder(Stream.from_byte_array(data)).read()
    assert not errors
    return messages["workout_step_mesgs"]


def test_native_app_workout_has_duration_value():
    steps = _decode(FIXTURES / "app.fit")
    timed = [s for s in steps if s.get("duration_type") == "time"]
    assert timed
    for step in timed:
        assert step["duration_value"] > 0
        assert step["duration_time"] > 0


def test_our_encoding_matches_native_duration_shape():
    doc = {
        "steps": [
            {"duration": 1200, "warmup": True, "power": {"start": 40, "end": 50, "units": "%ftp"}},
            {
                "reps": 2,
                "steps": [
                    {"duration": 600, "power": {"start": 70, "end": 80, "units": "%ftp"}},
                    {"duration": 300, "intensity": "recovery", "power": {"start": 50, "end": 60, "units": "%ftp"}},
                ],
            },
            {"duration": 600, "cooldown": True, "power": {"start": 40, "end": 50, "units": "%ftp"}},
        ],
    }
    fit_bytes = icu_workout_doc_to_bryton_fit("app", doc)
    assert fit_bytes is not None
    steps, errors = Decoder(Stream.from_byte_array(fit_bytes)).read()
    assert not errors
    timed = [s for s in steps["workout_step_mesgs"] if s.get("duration_type") == "time"]
    assert len(timed) == 4
    for step in timed:
        assert step["duration_value"] == step["duration_time"] * 1000
        assert step["target_type"] == 245
