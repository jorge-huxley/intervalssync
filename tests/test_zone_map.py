"""Tests for intervals.icu → iGPSPORT zone mapping."""

from __future__ import annotations

from intervalssync.igpsport.zone_map import (
    POWER_INTERIOR_CAP,
    POWER_LAST_ZONE_END,
    hr_upper_bounds_bpm,
    map_hr_zones,
    map_power_zones,
    power_upper_bounds_watts,
)


def _template_zones(count: int) -> list[dict]:
    return [{"id": index, "start": 0, "end": 0} for index in range(count)]


# settings-ride.json reference values
FTP = 242
POWER_PCT = [55, 75, 90, 105, 120, 999]
HR_BPM = [120, 146, 166, 185, 193]
MAX_HR = 193


def test_power_upper_bounds_from_settings_ride():
    assert power_upper_bounds_watts(POWER_PCT, FTP) == [133, 182, 218, 254, 290, 2418]


def test_hr_upper_bounds_from_settings_ride():
    assert hr_upper_bounds_bpm(HR_BPM, MAX_HR) == [120, 146, 166, 185, 193]


def test_map_power_same_count_seven_slots():
    zones = map_power_zones(POWER_PCT, FTP, _template_zones(6))
    assert len(zones) == 6
    assert zones[0]["start"] == 0 and zones[0]["end"] == 133
    assert zones[-1]["end"] == POWER_LAST_ZONE_END
    assert zones[-2]["end"] <= POWER_INTERIOR_CAP


def test_map_power_fewer_intervals_than_igpsport():
    zones = map_power_zones(POWER_PCT, FTP, _template_zones(7))
    assert len(zones) == 7
    assert zones[4]["end"] == 290
    assert zones[-1]["end"] == POWER_LAST_ZONE_END
    assert zones[-2]["end"] <= POWER_INTERIOR_CAP
    assert zones[-1]["start"] == zones[-2]["end"]


def test_map_power_more_intervals_than_igpsport():
    intervals_pct = [55, 65, 75, 85, 90, 105, 120]
    zones = map_power_zones(intervals_pct, FTP, _template_zones(5))
    assert len(zones) == 5
    assert zones[3]["end"] == int(round(FTP * 1.20))
    assert zones[3]["end"] <= POWER_INTERIOR_CAP
    assert zones[4]["start"] == zones[3]["end"]
    assert zones[4]["end"] == POWER_LAST_ZONE_END


def test_map_hr_same_count():
    zones = map_hr_zones(HR_BPM, MAX_HR, _template_zones(5))
    assert [zone["end"] for zone in zones] == [120, 146, 166, 185, 193]


def test_map_hr_fewer_intervals_than_igpsport():
    zones = map_hr_zones(HR_BPM[:3], MAX_HR, _template_zones(5))
    assert zones[2]["end"] == 166
    assert zones[-1]["end"] == MAX_HR
    assert zones[-2]["end"] == MAX_HR - 1


def test_map_hr_more_intervals_than_igpsport():
    intervals = [110, 130, 150, 165, 175, 185, MAX_HR]
    zones = map_hr_zones(intervals, MAX_HR, _template_zones(5))
    assert zones[3]["end"] == 165
    assert zones[4]["start"] == 165
    assert zones[4]["end"] == MAX_HR


def test_map_power_dedupes_equal_boundaries():
    zones = map_power_zones([55, 55, 75, 90, 105, 120], FTP, _template_zones(6))
    assert zones[0]["end"] == 133
    assert zones[1]["end"] > zones[0]["end"]


def test_map_power_preserves_zone_metadata():
    template = [{"id": "zone-a", "color": "#fff", "start": 99, "end": 999}]
    zones = map_power_zones([55], FTP, template)
    assert zones[0]["id"] == "zone-a"
    assert zones[0]["color"] == "#fff"
