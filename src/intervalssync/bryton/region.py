"""Bryton Active regional endpoints (international vs China).

Bryton runs fully separate account databases and Meteor deployments for its
international and China-region apps. An account that exists on one region's
server reports ``User not found`` on the other, so the user has to pick the
region where the account was created.

The China backend was found through the regional web clients:
``www.brytonsports.cn`` (百锐腾运动) talks to ``active.cn.brytonactive.com``,
which serves the same DDP API, mobile FIT endpoint and workout upload route as
the international deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BrytonRegionName = Literal["international", "china"]


@dataclass(frozen=True)
class BrytonRegionConfig:
    name: BrytonRegionName
    # Meteor DDP + mobile REST API (``GET /api/activity``).
    host: str
    # Web backend used for the planned-workout upload (``/workout/upload``).
    web_host: str


INTERNATIONAL = BrytonRegionConfig(
    name="international",
    host="m3.brytonactive.com",
    web_host="active.brytonsport.com",
)

CHINA = BrytonRegionConfig(
    name="china",
    host="active.cn.brytonactive.com",
    web_host="active.cn.brytonactive.com",
)

_REGIONS: dict[BrytonRegionName, BrytonRegionConfig] = {
    "international": INTERNATIONAL,
    "china": CHINA,
}


def resolve_region(name: str | None) -> BrytonRegionConfig:
    """Return the region config for a name; default is international."""
    if not name or name == "international":
        return INTERNATIONAL
    if name == "china":
        return CHINA
    raise ValueError(
        f"Unknown Bryton region: {name!r} (expected 'international' or 'china')"
    )
