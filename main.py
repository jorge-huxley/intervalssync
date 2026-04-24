import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from urllib.parse import unquote

load_dotenv()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


IGP_USER = os.environ["IGP_USER"]
IGP_PASS = os.environ["IGP_PASS"]
INTERVALS_KEY = os.getenv("INTERVALS_API_KEY")

STEP_LIST_ACTIVITIES = env_bool("STEP_LIST_ACTIVITIES", True)
STEP_GET_DOWNLOAD_URL = env_bool("STEP_GET_DOWNLOAD_URL", False)
STEP_DOWNLOAD_FIT = env_bool("STEP_DOWNLOAD_FIT", False)
STEP_UPLOAD_INTERVALS = env_bool("STEP_UPLOAD_INTERVALS", False)

MAX_ACTIVITIES = int(os.getenv("MAX_ACTIVITIES", "5"))

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)


session = requests.Session()


# 1. Login to iGPSPORT
r = session.post(
    "https://i.igpsport.com/Auth/Login",
    json={
        "username": IGP_USER,
        "password": IGP_PASS,
    },
)
r.raise_for_status()
print("Logged in to iGPSPORT")

# print("Cookies:", session.cookies.get_dict())

login_token = session.cookies.get("loginToken")
login_token = unquote(login_token)

auth_headers = {
    "Authorization": f"Bearer {login_token}",
}

# 2. Get activity list
r = session.get("https://i.igpsport.com/Activity/ActivityList")
r.raise_for_status()

data = r.json()
activities = data.get("item", [])[:MAX_ACTIVITIES]

if STEP_LIST_ACTIVITIES:
    print("\niGPSPORT activities:")
    for act in activities:
        ride_id = act.get("RideId")
        title = act.get("Title", f"iGPSPORT {ride_id}")
        start_time = act.get("StartTime") or act.get("StartDate") or "unknown date"

        print(f"- {ride_id} | {start_time} | {title}")


for act in activities:
    ride_id = act["RideId"]
    title = act.get("Title", f"iGPSPORT {ride_id}")

    fit_url = None
    fit_path = DOWNLOAD_DIR / f"igpsport_{ride_id}.fit"

    if STEP_GET_DOWNLOAD_URL or STEP_DOWNLOAD_FIT or STEP_UPLOAD_INTERVALS:
        # 3. Try getting activity detail first
        r = session.get(
            f"https://prod.en.igpsport.com/service/web-gateway/web-analyze/activity/queryActivityDetail/{ride_id}",
            headers=auth_headers,
        )

        print("Detail status:", r.status_code)

        if r.ok:
            detail = r.json()
            # print(detail)
            fit_url = detail.get("data", {}).get("fitUrl")
        else:
            print(r.text[:1000])
            fit_url = None

        # 4. Fallback: get download URL
        if not fit_url:
            r = session.get(
                f"https://prod.en.igpsport.com/service/web-gateway/web-analyze/activity/getDownloadUrl/{ride_id}",
                headers=auth_headers,
            )

            print("Download URL status:", r.status_code)

            if not r.ok:
                print(r.text[:1000])
                continue

            fit_url = r.json().get("data")

        if not fit_url:
            print(f"Could not get FIT URL for {ride_id}")
            continue

        if STEP_GET_DOWNLOAD_URL:
            print(f"\nDownload URL for {ride_id}:")
            print(fit_url)

    if STEP_DOWNLOAD_FIT or STEP_UPLOAD_INTERVALS:
        fit = requests.get(fit_url)
        fit.raise_for_status()

        fit_path.write_bytes(fit.content)
        print(f"Downloaded {ride_id} to {fit_path}")

    if STEP_UPLOAD_INTERVALS:
        if not INTERVALS_KEY:
            raise RuntimeError("INTERVALS_API_KEY is required for upload")

        with fit_path.open("rb") as f:
            r = requests.post(
                "https://intervals.icu/api/v1/athlete/0/activities",
                params={
                    "name": title,
                    "external_id": f"igpsport_{ride_id}",
                },
                files={
                    "file": (
                        fit_path.name,
                        f,
                        "application/octet-stream",
                    )
                },
                auth=("API_KEY", INTERVALS_KEY),
            )

        if r.status_code in (200, 201):
            print(f"Uploaded {ride_id}: {title}")
        else:
            print(f"Failed upload {ride_id}: {r.status_code} {r.text}")