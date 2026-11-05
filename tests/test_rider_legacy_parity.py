"""The selective command must not introduce a second zone policy."""

from copy import deepcopy

import pytest

from intervalssync import intervals_icu
from intervalssync.igpsport.profile_sync import apply_intervals_settings, build_rider_settings_plan, parse_rider_fields
from test_profile_sync import _rider_interval_destination, _rider_user_destination, _rider_source


@pytest.mark.parametrize("ftp,power,slots,expected", [
    (250, [55, 75, 90, 105, 120, 150, 999], 7, [138, 188, 225, 262, 300, 375, 2500]),
    (250.5, [55, 75, 90, 105, 120, 150, 999], 7, [138, 188, 225, 262, 300, 375, 2500]),
    (250, [53, 71, 89, 104, 123, 160, 999], 7, [132, 178, 222, 260, 308, 400, 2500]),
    # Five power slots are synthetic compatibility coverage, not live evidence.
    (250, [55, 75, 90, 105, 120, 150, 999], 5, [138, 188, 225, 375, 2500]),
])
@pytest.mark.parametrize("names", [None, ["Custom"] * 7, "unused malformed labels"])
def test_fetched_source_legacy_and_selective_zones_are_identical(ftp, power, slots, expected, names):
    data = {"ftp": ftp, "max_hr": 195.5, "lthr": 180.5,
        "power_zones": power, "hr_zones": [120, 140, 160, 175, 185, 190, 196],
        "power_zone_names": names, "hr_zone_names": names}
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return deepcopy(data)
    class Http:
        def get(self, *args, **kwargs):
            return Response()
    legacy_source = intervals_icu.fetch_sport_settings("synthetic", http=Http())
    selective_source = intervals_icu.fetch_sport_settings("synthetic", http=Http(), strict=True)
    destination = _rider_interval_destination()
    destination["power"] = destination["power"][:slots]
    destination["power"][-1]["end"] = 1800
    destination["member"]["heartRateComputeMode"] = 2
    before = deepcopy(destination)
    legacy = apply_intervals_settings(destination, legacy_source)
    _, athlete = _rider_source()
    plan = build_rider_settings_plan(selective_source, athlete, destination,
        _rider_user_destination(), parse_rider_fields("power_zones,hr_zones"))
    assert plan.interval_body["power"] == legacy["power"]
    assert [row["end"] for row in plan.interval_body["power"]] == expected
    assert plan.interval_body["heartRate"] == legacy["heartRate"]
    assert [row["end"] for row in plan.interval_body["heartRate"]] == [120, 140, 160, 175, 196]
    assert plan.interval_body["member"]["heartRateComputeMode"] == legacy["member"]["heartRateComputeMode"] == 0
    assert plan.interval_body["member"]["ftp"] == 250
    assert plan.interval_body["member"]["lthr"] == 180
    assert plan.interval_body["heartRateReserve"] == before["heartRateReserve"]
    assert plan.interval_body["heartRateLactateThreshold"] == before["heartRateLactateThreshold"]
    assert destination == before


@pytest.mark.parametrize("fields", ["weight", "ftp"])
def test_non_hr_selection_preserves_hr_mode_and_all_tables(fields):
    sport, athlete = _rider_source()
    destination = _rider_interval_destination()
    destination["member"]["heartRateComputeMode"] = 2
    plan = build_rider_settings_plan(sport, athlete, destination,
        _rider_user_destination(), parse_rider_fields(fields))
    assert plan.interval_body["member"]["heartRateComputeMode"] == 2
    for table in ("heartRate", "heartRateReserve", "heartRateLactateThreshold", "power"):
        assert plan.interval_body[table] == destination[table]
