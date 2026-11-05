# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**Intervals Sync** — a cross-platform app that syncs cycling activities to **intervals.icu** from **iGPSPORT** or **Bryton Active**, and can upload planned workouts from intervals.icu back to iGPSPORT. It ships as a **Flet** GUI (`intervalssync-gui`) plus a headless **CLI** (`intervalssync`). Dependency management uses [uv](https://docs.astral.dev/uv/) (Python 3.13).

## Commands

```bash
uv sync
uv run intervalssync-gui
uv run intervalssync sync                          # iGPSPORT (default)
uv run intervalssync sync --source bryton          # Bryton Active
uv run intervalssync upload-workouts --json        # intervals.icu → iGPSPORT
uv run intervalssync sync-zones --env-file .env --json   # intervals.icu → iGPSPORT profile
uv run intervalssync check --source bryton
uv run flet build windows
uv run pytest
```

## Tests

`pytest` under `tests/` — offline, no network. iGPSPORT tests in `test_igpsport_core.py`; Bryton in `test_bryton_core.py`. Config tests redirect `CONFIG_PATH` to a tmp dir.

## Architecture

Package root: `src/intervalssync/`. **CLI** and **GUI** are separate subpackages; **activity sources** are sibling subpackages under the root.

```
src/intervalssync/
  cli/main.py, env.py, config.py                 # headless CLI
  gui/app.py, views, config.py, secrets.py       # Flet UI (dual-source: iGPSPORT + Bryton)
  igpsport/core.py, workout.py                   # iGPSPORT source
  bryton/ddp.py, api.py, core.py, region.py      # Bryton source
  intervals_icu.py, dropbox_client.py            # shared by sources
```

- **`intervals_icu.py`** — shared upload, skip-existing (`external_id`), sport PUT, calendar workout fetch, sport-settings lookup (`fetch_sport_settings`, `max_hr`).
- **`igpsport/core.py`** — `sync(SyncConfig, progress)`: login → list → FIT URL → download → upload. `external_id`: `igpsport_{ride_id}`.
- **`igpsport/profile_sync.py`** — `sync_profile_zones`: intervals.icu sport settings + athlete weight → iGPSPORT profile thresholds/zones/weight.
- **`igpsport/workout.py`** — planned workouts intervals.icu → iGPSPORT.
- **`bryton/ddp.py`** — Meteor DDP login + `activityList` subscription. `region.py` holds the international vs China endpoints.
- **`bryton/api.py`** — `GET https://{session.host}/api/activity?id=…` (FIT download; Android app API).
- **`bryton/core.py`** — `sync(SyncConfig, progress)`. `external_id`: `bryton_{activity_id}`.
- **`gui/secrets.py`** — async OS vault via `flet-secure-storage`.
- **`gui/config.py`** — GUI JSON settings: `enable_igpsport` / `enable_bryton`, per-source usernames, shared sync options.
- **`gui/sync_view.py`** — dispatches to `igpsport.core.sync` or `bryton.core.sync` per enabled source; workout upload is iGPSPORT-only.
- **`cli/env.py`** — `.env` credential loading for the headless CLI.

## iGPSPORT API notes

1. **International:** POST `i.igpsport.com/Auth/Login` → `loginToken` cookie URL-decoded as Bearer token.
2. **China:** POST `prod.zh.igpsport.com/service/auth/account/login` with `{appId, username, password}` → JSON `data.access_token` as Bearer.
3. `Activity/ActivityList` (intl) or `queryMyActivity` (China) — PascalCase / camelCase field names respectively.
4. FIT URL: `{prod.en|zh}.igpsport.com/.../queryActivityDetail/{id}` or `getDownloadUrl/{id}`.

## Bryton API notes

1. Login: Meteor DDP `login` with email + SHA-256 password digest on `m3.brytonactive.com` (international) or `active.cn.brytonactive.com` (China).
2. List: subscribe `activityList` → `userActivities` collection.
3. FIT: REST `GET /api/activity?id={_id}` with `X-User-Id`, `X-Auth-Token`, static `x-api-key` (not the web `activity.detail.2` samples API).
4. Workouts: POST `https://{web_host}/workout/upload/{user_id}` (`active.brytonsport.com` international, `active.cn.brytonactive.com` China).
5. **Regions are fully separate account databases.** An account created in one region returns `User not found` in the other. GUI `bryton_region`; CLI `INTERVALSSYNC_BRYTON_REGION=international|china`.

## Flet version note

Built against Flet 0.86.x. Uses `ft.Icons` / `ft.Colors`, `page.show_dialog`, `ft.run(main)`.

## Verified rider-settings CLI

`sync-rider-settings` transfers selected cycling settings from intervals.icu to
 iGPSPORT, with dependencies and read-back verification (`Ride` only). Missing
source values preserve destination fields. Zone conversion, threshold rounding,
power caps, and selected HR-zone mode reuse the legacy sync behavior; labels do
not gate valid numeric configurations.
Values may be printed only with explicit `--dry-run --show-values`; normal/error
output is status-only. Legacy `sync-zones` parsing and behavior remain unchanged.
