"""iGPSPORT regional endpoints (international vs China)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

IgpRegionName = Literal["international", "china"]


@dataclass(frozen=True)
class IgpRegionConfig:
    name: IgpRegionName
    login_url: str
    activity_query_url: str
    gateway_base: str
    mobile_api_base: str
    accept_language: str

    @property
    def workout_list_url(self) -> str:
        return f"{self.mobile_api_base}/WorkOut/CustomWorkout"

    @property
    def workout_edit_url(self) -> str:
        return f"{self.mobile_api_base}/WorkOut/EditCustomWorkOut"

    @property
    def get_interval_url(self) -> str:
        return f"{self.mobile_api_base}/v2/User/UserIntervalInfo"

    @property
    def update_interval_url(self) -> str:
        return f"{self.mobile_api_base}/User/UpdatePersonalIntervalInfo"

    @property
    def user_info_url(self) -> str:
        return f"{self.mobile_api_base}/User/UserInfo"

    @property
    def update_personal_user_info_url(self) -> str:
        # App profile editor saves weight/height/etc here (not UpdateUserInfo).
        return f"{self.mobile_api_base}/User/UpdatePersonalUserInfo"


INTERNATIONAL = IgpRegionConfig(
    name="international",
    login_url="https://prod.en.igpsport.com/service/auth/account/login",
    activity_query_url=(
        "https://prod.en.igpsport.com/service/web-gateway/web-analyze/activity/queryMyActivity"
    ),
    gateway_base="https://prod.en.igpsport.com/service/web-gateway/web-analyze/activity",
    mobile_api_base="https://prod.en.igpsport.com/service/mobile/api",
    accept_language="en",
)

CHINA = IgpRegionConfig(
    name="china",
    login_url="https://prod.zh.igpsport.com/service/auth/account/login",
    activity_query_url=(
        "https://prod.zh.igpsport.com/service/web-gateway/web-analyze/activity/queryMyActivity"
    ),
    gateway_base="https://prod.zh.igpsport.com/service/web-gateway/web-analyze/activity",
    mobile_api_base="https://prod.zh.igpsport.com/service/mobile/api",
    accept_language="zh-CN",
)

_REGIONS: dict[IgpRegionName, IgpRegionConfig] = {
    "international": INTERNATIONAL,
    "china": CHINA,
}


def resolve_region(name: str | None) -> IgpRegionConfig:
    """Return the region config for a name; default is international."""
    if not name or name == "international":
        return INTERNATIONAL
    if name == "china":
        return CHINA
    raise ValueError(f"Unknown iGPSPORT region: {name!r} (expected 'international' or 'china')")
