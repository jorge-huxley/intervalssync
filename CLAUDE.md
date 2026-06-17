# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A cross-platform app that syncs cycling activities and planned workouts between iGPSPORT and intervals.icu. It ships as a **Flet** GUI (Python, renders via Flutter — desktop now, Android/iOS later) plus a headless **CLI** for automation. Dependency/environment management is done with [uv](https://docs.astral.dev/uv/) (Python 3.13).

## Commands

```bash
uv sync                 # install/lock dependencies into .venv
uv run main.py          # launch the GUI
uv run igpsync sync --json              # headless activity sync
uv run igpsync upload-workouts --json   # headless workout upload
uv run igpsync check                    # validate CLI credentials
uv run flet build windows   # build the distributable Windows .exe (build/windows/)
uv run pytest               # run the test suite
```

`flet build apk` / `flet build ipa` target Android/iOS from the same code.

## Tests

`pytest` suite under `tests/`, run with `uv run pytest` (also runs in CI on every push/PR via `.github/workflows/test.yml`). Tests are offline: leaf HTTP helpers are tested by faking `core.requests`, and `sync()` is tested by monkeypatching the leaf functions it calls (see the `stub_sync` fixture in `tests/test_core.py`). No network, no real credentials. Config tests redirect `config.CONFIG_PATH` to a tmp dir. `pythonpath = ["src"]` is set in pyproject so imports work without installing.

## Architecture — three layers (the key design)

The code is split so that going mobile later changes mostly just packaging; core, storage, and most UI stay put. All packages live under `src/igpsync/`.

- **Core (`core.py`)** — pure activity sync logic, no UI and no module-level side effects. `sync(SyncConfig, progress)` drives the four steps and reports via a `progress(message)` callback so callers can render it however they like. Raises `SyncError` / `AuthError` for friendly messages. Functions: `login`, `list_activities`, `resolve_fit_url`, `download_fit`, `upload_to_intervals`.
- **Workouts (`workout.py`)** — planned workout upload (intervals.icu → iGPSPORT). `upload_workouts(WorkoutUploadConfig, progress)` fetches calendar events and pushes custom workouts via the iGPSPORT mobile JSON API. UI-free; used by GUI and CLI.
- **CLI (`cli.py`, `cli_env.py`, `cli_config.py`)** — headless `igpsync` entry with `check`, `sync`, and `upload-workouts` subcommands. Credentials from `.env`; non-secret settings in `igpsync-cli` `config.json`. See `docs/AGENT.md`.
- **Storage**
  - `secrets.py` — `SecretStore` **async** ABC + `FletSecureStorage`. Secrets (`igp_password`, `intervals_api_key`) live in the **OS-native vault** via the `flet-secure-storage` service (Windows Credential Manager / macOS+iOS Keychain / Android Keystore / Linux libsecret), never in a file. Same backend on every platform — no per-OS branching. It's async and page-bound, so the `SecureStorage` service must be registered (`page.services.append(...)`) before use and all secret access is `await`ed.
  - `config.py` — non-secret GUI settings (`igp_user`, step toggles, `max_activities`, `download_dir`, `activity_type`, `uploaded_workouts`, `workout_days_ahead`) as JSON in `platformdirs.user_config_dir`.
- **GUI (`gui/`)** — `app.py` (async entry `ft.run(_app)`, Material 3 theme, app-bar routing; registers the secure-storage service), `settings_view.py` (async; credential inputs → secure storage), `sync_view.py` ("Sync activities" and "Upload workouts", progress bar + live log). Because secret access is async but `core.sync` runs on a worker thread via `page.run_thread`, the sync view resolves secrets to plain strings in the async click handler and passes them into the thread. First run with no saved credentials opens Settings. Uses the **imperative** Flet style; the 0.85 declarative `@ft.component` / `ft.use_dialog` API is an alternative we don't use.
- **`main.py`** — entry shim that puts `src/` on the path and launches the GUI (`igpsync.gui.app.main`).

## Flow / external API notes

Unchanged from the original script, now in `core.py`:

1. **Auth**: POST `i.igpsport.com/Auth/Login`. The `loginToken` cookie is URL-decoded (`unquote`) and reused as a `Bearer` token for the gateway API — this cookie-to-token step is non-obvious and required.
2. **Activity list**: `i.igpsport.com/Activity/ActivityList` returns `{"item": [...]}` with PascalCase keys (`RideId`, `Title`, `StartTime`).
3. **FIT URL resolution** uses a different host (`prod.en.igpsport.com/service/web-gateway/...`): try `queryActivityDetail/{id}`, fall back to `getDownloadUrl/{id}`.
4. **Upload**: intervals.icu uses HTTP basic auth with literal username `"API_KEY"`; the API key is the password. Files are named `igpsport_{ride_id}.fit` and the id is sent as `external_id` for idempotency.
5. **Skip already-uploaded**: before downloading, `GET /api/v1/athlete/0/activities?oldest=…&newest=…` lists existing activities; the response includes the `external_id` we set, so rides already present (`igpsport_{ride_id}`) are skipped unless `force_resync` is set.

### intervals.icu API docs

- Swagger reference: https://intervals.icu/api-docs.html (JS-rendered — open in a browser or query the live API to inspect response shapes; WebFetch can't read it).
- API integration cookbook (forum): https://forum.intervals.icu/t/intervals-icu-api-integration-cookbook/80090

## Flet version note

Built against Flet 0.85.x. That line renamed some control props (e.g. `TextField.helper_text` → `helper`), uses `ft.Icons` / `ft.Colors` (capitalized) and `page.window.width`, replaced `page.open(dialog)` with **`page.show_dialog(dialog)`** / `page.pop_dialog()`, and made `ft.run(main)` the entry point (`ft.app(target=...)` still works as a shim). `SnackBar` is a `DialogControl`, so it is shown via `page.show_dialog(...)`. When editing the GUI, verify control kwargs against the installed version rather than older tutorials.
