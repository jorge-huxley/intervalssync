# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A cross-platform app that syncs cycling activities to **intervals.icu** from **iGPSPORT** or **Bryton Active**, and can upload planned workouts from intervals.icu back to iGPSPORT. It ships as a **Flet** GUI plus a headless **CLI** (`intervalssync`). Dependency management uses [uv](https://docs.astral.dev/uv/) (Python 3.13).

## Commands

```bash
uv sync
uv run main.py
uv run intervalssync sync                          # iGPSPORT (default)
uv run intervalssync sync --source bryton          # Bryton Active
uv run intervalssync upload-workouts --json        # intervals.icu → iGPSPORT
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
  bryton/ddp.py, api.py, core.py                 # Bryton source
  intervals_icu.py, dropbox_client.py            # shared by sources
```

- **`intervals_icu.py`** — shared upload, skip-existing (`external_id`), sport PUT, calendar workout fetch, sport-settings lookup (`max_hr`).
- **`igpsport/core.py`** — `sync(SyncConfig, progress)`: login → list → FIT URL → download → upload. `external_id`: `igpsport_{ride_id}`.
- **`igpsport/workout.py`** — planned workouts intervals.icu → iGPSPORT.
- **`bryton/ddp.py`** — Meteor DDP login + `activityList` subscription.
- **`bryton/api.py`** — `GET https://m3.brytonactive.com/api/activity?id=…` (FIT download; Android app API).
- **`bryton/core.py`** — `sync(SyncConfig, progress)`. `external_id`: `bryton_{activity_id}`.
- **`gui/secrets.py`** — async OS vault via `flet-secure-storage`.
- **`gui/config.py`** — GUI JSON settings: `enable_igpsport` / `enable_bryton`, per-source usernames, shared sync options.
- **`gui/sync_view.py`** — dispatches to `igpsport.core.sync` or `bryton.core.sync` per enabled source; workout upload is iGPSPORT-only.
- **`cli/env.py`** — `.env` credential loading for the headless CLI.

## iGPSPORT API notes

1. POST `i.igpsport.com/Auth/Login` → `loginToken` cookie URL-decoded as Bearer token.
2. `Activity/ActivityList` — PascalCase `RideId`, `Title`, `StartTime`.
3. FIT URL: `prod.en.igpsport.com/.../queryActivityDetail/{id}` or `getDownloadUrl/{id}`.

## Bryton API notes

1. Login: Meteor DDP `login` with email + SHA-256 password digest on `m3.brytonactive.com`.
2. List: subscribe `activityList` → `userActivities` collection.
3. FIT: REST `GET /api/activity?id={_id}` with `X-User-Id`, `X-Auth-Token`, static `x-api-key` (not the web `activity.detail.2` samples API).

## Flet version note

Built against Flet 0.85.x. Uses `ft.Icons` / `ft.Colors`, `page.show_dialog`, `ft.run(main)`.
