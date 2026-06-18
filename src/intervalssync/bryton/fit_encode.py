"""Encode intervals.icu workout_doc into Bryton-compatible FIT workouts.

Bryton Active stores uploaded FIT files as-is. Generic FIT exports (e.g. from
intervals.icu) parse partially in the web UI but fail on mobile and omit the
workout chart. Bryton's own web app re-encodes imported FIT via
``parseToEncodeData`` + ``encodeToFit`` before upload; we mirror that here by
building Bryton-native workout steps from ``workout_doc``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from garmin_fit_sdk import Encoder, Profile

# Bryton custom target_type values (see woParser.js in Bryton web bundle).
TARGET_FTP = 245
TARGET_LTHR = 248
TARGET_MHR = 249

# Percentage targets (FTP, LTHR, MHR) use custom values + 100_000.
BRYTON_FTP_OFFSET = 100_000

# Bryton Active mobile ignores LTHR (248) and shows 0 % — encode HR as % MHR (249).
# Dev toggle: set to "lthr" to restore LTHR encoding.
_BRYTON_HR_TARGET: Literal["mhr", "lthr"] = "mhr"


def bryton_hr_uses_mhr() -> bool:
    return _BRYTON_HR_TARGET == "mhr"


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _step_name(step: dict[str, Any], index: int) -> str:
    text = str(step.get("text") or "").strip()
    if text:
        return text[:16]
    intensity = str(step.get("intensity") or "").lower()
    if step.get("warmup") or intensity == "warmup":
        return "Warm Up"
    if step.get("cooldown") or intensity == "cooldown":
        return "Cool Down"
    if intensity in ("rest", "recovery"):
        return "Recovery"
    return "Work"


def _intensity(step: dict[str, Any]) -> str:
    intensity = str(step.get("intensity") or "").lower()
    if step.get("warmup") or intensity == "warmup":
        return "warmup"
    if step.get("cooldown") or intensity == "cooldown":
        return "cooldown"
    if intensity in ("rest", "recovery"):
        return "rest"
    return "active"


def _ftp_target_range(min_pct: int, max_pct: int) -> tuple[int, int, int]:
    if min_pct > max_pct:
        min_pct, max_pct = max_pct, min_pct
    return (
        TARGET_FTP,
        min_pct + BRYTON_FTP_OFFSET,
        max_pct + BRYTON_FTP_OFFSET,
    )


def _power_range(step: dict[str, Any]) -> tuple[int, int, int] | None:
    """Return Bryton % FTP targets from explicit ``%ftp`` power fields."""
    power = step.get("power")
    resolved = step.get("_power")

    if not isinstance(power, dict):
        return None

    units = str(power.get("units") or "").lower()
    pct_start = _num(power.get("start"))
    pct_end = _num(power.get("end"))
    pct_value = _num(power.get("value"))

    if units != "%ftp":
        return None

    min_pct: int | None
    max_pct: int | None

    if pct_start is not None and pct_end is not None:
        min_pct = int(pct_start)
        max_pct = int(pct_end)
    elif pct_value is not None and isinstance(resolved, dict):
        w_start = _num(resolved.get("start"))
        w_end = _num(resolved.get("end"))
        w_value = _num(resolved.get("value"))
        if w_start is not None and w_end is not None:
            ref = w_value
            if ref is None or ref == 0:
                ref = (w_start + w_end) / 2
            if ref and ref != 0:
                min_pct = int(round(w_start / ref * pct_value))
                max_pct = int(round(w_end / ref * pct_value))
            else:
                min_pct = max_pct = int(pct_value)
        else:
            min_pct = max_pct = int(pct_value)
    elif pct_value is not None:
        min_pct = max_pct = int(pct_value)
    else:
        return None

    return _ftp_target_range(min_pct, max_pct)


def _power_range_from_resolved(
    step: dict[str, Any],
    ftp: float | None,
) -> tuple[int, int, int] | None:
    """Return Bryton % FTP targets from resolved watts in ``_power``.

    intervals.icu provides resolved watt ranges in ``_power`` and athlete FTP
    on the workout doc when ``resolve=true``. Covers ``power_zone`` and any
    other non-``%ftp`` power units (mirrors ``_hr_range`` + LTHR).
    """
    if not ftp or ftp <= 0:
        return None

    resolved = step.get("_power")
    if not isinstance(resolved, dict):
        return None

    start = _num(resolved.get("start"))
    end = _num(resolved.get("end"))
    value = _num(resolved.get("value"))
    min_w = start if start is not None else value
    max_w = end if end is not None else value
    if min_w is None and max_w is None:
        return None
    min_w = min_w if min_w is not None else max_w
    max_w = max_w if max_w is not None else min_w

    min_pct = int(round(min_w / ftp * 100))
    max_pct = int(round(max_w / ftp * 100))

    return _ftp_target_range(min_pct, max_pct)


def _hr_range(
    step: dict[str, Any],
    *,
    lthr: float | None,
    max_hr: float | None,
) -> tuple[int, int, int] | None:
    """Return (target_type, low, high) as % HR reference with Bryton offsets.

    Bryton encodes HR targets as custom percentages (target_type 248 = % LTHR,
    249 = % MHR; values + 100_000), not absolute BPM (target_type 1, + 100).
    intervals.icu provides resolved BPM in ``_hr`` and athlete ``lthr`` /
    ``max_hr`` on the workout doc when ``resolve=true``.
    """
    if _BRYTON_HR_TARGET == "lthr":
        hr_ref = lthr
        target_type = TARGET_LTHR
    else:
        hr_ref = max_hr
        target_type = TARGET_MHR

    if not hr_ref or hr_ref <= 0:
        return None

    resolved = step.get("_hr")
    if not isinstance(resolved, dict):
        return None

    start = _num(resolved.get("start"))
    end = _num(resolved.get("end"))
    value = _num(resolved.get("value"))
    min_bpm = start if start is not None else value
    max_bpm = end if end is not None else value
    if min_bpm is None and max_bpm is None:
        return None
    min_bpm = min_bpm if min_bpm is not None else max_bpm
    max_bpm = max_bpm if max_bpm is not None else min_bpm
    if min_bpm > max_bpm:
        min_bpm, max_bpm = max_bpm, min_bpm

    min_pct = int(round(min_bpm / hr_ref * 100))
    max_pct = int(round(max_bpm / hr_ref * 100))
    return (
        target_type,
        min_pct + BRYTON_FTP_OFFSET,
        max_pct + BRYTON_FTP_OFFSET,
    )


def _target_fields(
    step: dict[str, Any],
    *,
    ftp: float | None,
    lthr: float | None,
    max_hr: float | None,
) -> dict[str, Any]:
    power = _power_range(step) or _power_range_from_resolved(step, ftp)
    if power:
        target_type, low, high = power
        return {
            "target_type": target_type,
            "target_value": 0,
            "custom_target_value_low": low,
            "custom_target_value_high": high,
        }

    hr = _hr_range(step, lthr=lthr, max_hr=max_hr)
    if hr:
        target_type, low, high = hr
        return {
            "target_type": target_type,
            "target_value": 0,
            "custom_target_value_low": low,
            "custom_target_value_high": high,
        }

    return {
        "target_type": "open",
        "target_value": 0,
    }


def _timed_step(
    step: dict[str, Any],
    index: int,
    *,
    ftp: float | None,
    lthr: float | None,
    max_hr: float | None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if step.get("until_lap_press"):
        mesg: dict[str, Any] = {
            "message_index": index,
            "wkt_step_name": name or _step_name(step, index + 1),
            "duration_type": "open",
            "duration_value": 0,
            "intensity": _intensity(step),
        }
        mesg.update(_target_fields(step, ftp=ftp, lthr=lthr, max_hr=max_hr))
        return mesg

    duration = step.get("duration")
    if duration is None:
        return None

    mesg = {
        "message_index": index,
        "wkt_step_name": name or _step_name(step, index + 1),
        "duration_type": "time",
        "duration_value": int(duration) * 1000,
        "intensity": _intensity(step),
    }
    mesg.update(_target_fields(step, ftp=ftp, lthr=lthr, max_hr=max_hr))
    return mesg


def _flatten_steps(
    raw_steps: list[Any],
    *,
    ftp: float | None,
    lthr: float | None,
    max_hr: float | None,
) -> list[dict[str, Any]] | None:
    """Expand intervals.icu steps (including repeats) into Bryton FIT messages."""
    out: list[dict[str, Any]] = []

    def append_repeat(start_index: int, repeat_count: int) -> None:
        out.append(
            {
                "message_index": len(out),
                "duration_type": "repeat_until_steps_cmplt",
                "duration_value": start_index,
                "target_value": int(repeat_count),
            }
        )

    for step in raw_steps:
        if not isinstance(step, dict):
            continue

        reps = step.get("reps")
        nested = step.get("steps")
        if reps and isinstance(nested, list) and nested:
            start_index = len(out)
            for child in nested:
                if not isinstance(child, dict):
                    continue
                mapped = _timed_step(
                    child, len(out), ftp=ftp, lthr=lthr, max_hr=max_hr
                )
                if mapped is None:
                    return None
                out.append(mapped)
            if len(out) == start_index:
                return None
            append_repeat(start_index, int(reps))
            continue

        mapped = _timed_step(step, len(out), ftp=ftp, lthr=lthr, max_hr=max_hr)
        if mapped is None:
            return None
        out.append(mapped)

    return out or None


def icu_workout_doc_to_bryton_fit(
    name: str,
    workout_doc: dict[str, Any],
    *,
    max_hr: float | None = None,
) -> bytes | None:
    """Build a Bryton-compatible workout FIT file from intervals.icu workout_doc."""
    raw_steps = workout_doc.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None

    lthr = _num(workout_doc.get("lthr"))
    if max_hr is None:
        max_hr = _num(workout_doc.get("max_hr"))
    ftp = _num(workout_doc.get("ftp"))
    steps = _flatten_steps(raw_steps, ftp=ftp, lthr=lthr, max_hr=max_hr)
    if not steps:
        return None

    wkt_name = name.strip() or "Workout"
    encoder = Encoder()
    encoder.on_mesg(
        Profile["mesg_num"]["FILE_ID"],
        {
            "type": "workout",
            "manufacturer": "bryton",
            "serial_number": 255,
            "time_created": datetime.now(tz=timezone.utc),
        },
    )
    encoder.on_mesg(
        Profile["mesg_num"]["WORKOUT"],
        {
            "sport": "cycling",
            "num_valid_steps": len(steps),
            "wkt_name": wkt_name,
        },
    )
    for step in steps:
        encoder.on_mesg(Profile["mesg_num"]["WORKOUT_STEP"], step)

    return bytes(encoder.close())
