"""Map intervals.icu zone definitions onto iGPSPORT fixed zone slots."""

from __future__ import annotations

from typing import Any

POWER_INTERIOR_CAP = 1999
POWER_LAST_ZONE_END = 2500


def power_upper_bounds_watts(power_zones_pct: list[float], ftp: float) -> list[int]:
    """Convert intervals % FTP upper bounds to absolute watt boundaries."""
    if ftp <= 0 or not power_zones_pct:
        return []
    return [int(round(ftp * pct / 100)) for pct in power_zones_pct]


def hr_upper_bounds_bpm(hr_zones_bpm: list[float], max_hr: float) -> list[int]:
    """Return intervals HR zone upper bounds capped at max_hr."""
    if max_hr <= 0 or not hr_zones_bpm:
        return []
    cap = int(round(max_hr))
    bounds = [int(round(bpm)) for bpm in hr_zones_bpm]
    bounds[-1] = min(bounds[-1], cap)
    return bounds


def _prepare_intervals_ends(intervals_ends: list[int], slot_count: int, cap: int) -> list[int]:
    """Drop open-ended last intervals bound when extra iGPSPORT slots need the cap."""
    ends = list(intervals_ends)
    n = len(ends)
    p = slot_count
    pad_count = p - n
    if pad_count > 0 and n >= 2 and ends[-1] >= cap - pad_count:
        ends = ends[:-1]
    return ends


def _enforce_strictly_increasing(ends: list[int], cap: int) -> list[int]:
    """Ensure zone end values strictly increase and the last is capped."""
    if not ends:
        return ends
    out = [int(value) for value in ends]
    for index in range(1, len(out)):
        if out[index] <= out[index - 1]:
            out[index] = out[index - 1] + 1
    out[-1] = min(out[-1], cap)
    if len(out) > 1 and out[-1] <= out[-2]:
        index = len(out) - 2
        while index > 0 and out[index] >= out[index + 1]:
            out[index] = out[index + 1] - 1
            index -= 1
        if out[0] >= out[1]:
            out[0] = max(0, out[1] - 1)
    return out


def _slot_end_values(intervals_ends: list[int], slot_count: int, cap: int) -> list[int]:
    """Map intervals zone count onto a fixed iGPSPORT slot count."""
    if slot_count <= 0:
        return []
    if not intervals_ends:
        return list(range(cap, cap - slot_count, -1))

    ends = _prepare_intervals_ends(intervals_ends, slot_count, cap)
    n = len(ends)
    p = slot_count
    pad_count = p - n

    if n == p:
        result = list(ends)
    elif n < p:
        result = list(ends)
        for index in range(pad_count):
            result.append(cap - pad_count + 1 + index)
    else:
        result = list(ends[: p - 1])
        result.append(ends[-1])

    return _enforce_strictly_increasing(result, cap)


def _apply_end_values(
    end_values: list[int],
    igpsport_zones: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rewrite start/end on iGPSPORT zone dicts, preserving other fields."""
    out: list[dict[str, Any]] = []
    start = 0
    for index, zone in enumerate(igpsport_zones):
        if not isinstance(zone, dict):
            continue
        updated = dict(zone)
        updated["start"] = start
        updated["end"] = end_values[index]
        start = end_values[index]
        out.append(updated)
    return out


def map_power_zones(
    intervals_pct: list[float],
    ftp: float,
    igpsport_zones: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map intervals.icu power zones onto iGPSPORT power slots."""
    if not igpsport_zones:
        return []
    intervals_ends = power_upper_bounds_watts(intervals_pct, ftp)
    slot_count = len(igpsport_zones)
    if slot_count == 1:
        slot_ends = [POWER_LAST_ZONE_END]
    else:
        interior = _slot_end_values(intervals_ends, slot_count - 1, POWER_INTERIOR_CAP)
        interior[-1] = min(interior[-1], POWER_INTERIOR_CAP)
        interior = _enforce_strictly_increasing(interior, POWER_INTERIOR_CAP)
        slot_ends = interior + [POWER_LAST_ZONE_END]
    return _apply_end_values(slot_ends, igpsport_zones)


def map_hr_zones(
    intervals_bpm: list[float],
    max_hr: float,
    igpsport_zones: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map intervals.icu HR zones onto iGPSPORT heart-rate slots."""
    if not igpsport_zones:
        return []
    cap = int(round(max_hr))
    intervals_ends = hr_upper_bounds_bpm(intervals_bpm, max_hr)
    slot_ends = _slot_end_values(intervals_ends, len(igpsport_zones), cap)
    return _apply_end_values(slot_ends, igpsport_zones)
