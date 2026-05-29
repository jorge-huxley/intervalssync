# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A cross-platform app that exports cycling activities from iGPSPORT and uploads them to intervals.icu. It ships as a **Flet** GUI (Python, renders via Flutter — desktop now, Android/iOS later). Dependency/environment management is done with [uv](https://docs.astral.dev/uv/) (Python 3.13).

## Commands

```bash
uv sync                 # install/lock dependencies into .venv
uv run main.py          # launch the GUI
uv run flet build windows   # build the distributable Windows .exe (build/windows/)
uv run pytest               # run the test suite
```

`flet build apk` / `flet build ipa` target Android/iOS from the same code.

## Tests

`pytest` suite under `tests/`, run with `uv run pytest` (also runs in CI on every push/PR via `.github/workflows/test.yml`). Tests are offline: leaf HTTP helpers are tested by faking `core.requests`, and `sync()` is tested by monkeypatching the leaf functions it calls (see the `stub_sync` fixture in `tests/test_core.py`). No network, no real credentials. Config tests redirect `config.CONFIG_PATH` to a tmp dir. `pythonpath = ["src"]` is set in pyproject so imports work without installing.

## Architecture — three layers (the key design)

The code is split so that going mobile later changes only packaging and the secret-storage backend; core and most UI stay put. All packages live under `src/igpsync/`.

- **Core (`core.py`)** — pure sync logic, no UI and no module-level side effects. `sync(SyncConfig, progress)` drives the four steps and reports via a `progress(message)` callback so callers can render it however they like. Raises `SyncError` / `AuthError` for friendly messages. Functions: `login`, `list_activities`, `resolve_fit_url`, `download_fit`, `upload_to_intervals`.
- **Storage**
  - `secrets.py` — `SecretStore` ABC + `KeyringSecretStore`. Secrets (`igp_password`, `intervals_api_key`) live in the **OS-native vault** via `keyring` (Windows Credential Manager / macOS Keychain), never in a file. The ABC is the seam: a future `FletSecureStorage` mobile backend drops in without touching core or UI.
  - `config.py` — non-secret settings (`igp_user`, step toggles, `max_activities`, `download_dir`) as JSON in `platformdirs.user_config_dir`.
- **GUI (`gui/`)** — `app.py` (entry `ft.run(_app)`, Material 3 theme, app-bar routing between views), `settings_view.py` (credential inputs → keyring), `sync_view.py` (one-click "Sync activities", progress bar + live log; runs `core.sync` on a background thread). First run with no saved credentials opens Settings. Uses the **imperative** Flet style (explicit `page` mutation); the 0.85 declarative `@ft.component` / `ft.use_dialog` API is an alternative we don't use.
- **`main.py`** — entry shim that puts `src/` on the path and launches the GUI (`igpsync.gui.app.main`). The GUI is the only entry point.

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
