# iGPSPORT → intervals.icu

A small, friendly app that syncs your cycling activities from **iGPSPORT** to
**intervals.icu**. It's built for non-technical riders — no command line, no config
files: enter your credentials once, press **Sync**, and your latest rides land on
intervals.icu. Free and open source, for **Windows** and **Android**.

## Features

- Lists your recent iGPSPORT activities and uploads the original `.fit` files to intervals.icu
- **Skips activities already uploaded** so re-running is safe — with an optional *force re-sync*
- Lets you choose how many recent activities to process
- **Sets the intervals.icu sport type** after upload (e.g. Mountain Bike Ride / Gravel Ride) — iGPSPORT exports everything as a generic "Ride"
- Optionally deletes the local `.fit` files after a successful upload
- Stores your credentials in the **OS secure vault** (Windows Credential Manager / Android Keystore), never in a file
- Lets you know when a newer version is available

> Prefer the terminal, or want to help out? It's open source (Python + [Flet](https://flet.dev), MIT) — see [Run from source](#run-from-source), [Agent / headless sync](docs/AGENT.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

## Download & run (Windows)

1. Go to the [Releases](../../releases) page and download the latest `.zip`.
2. Unzip it anywhere and double-click the app (e.g. `igpsync.exe`).
3. On first launch, open **Settings** and enter:
   - your iGPSPORT **email** and **password**
   - your intervals.icu **API key** (intervals.icu → Settings → Developer)
4. Click **Save**, then go back and press **Sync activities**.

Your password and API key are stored in your operating system's **secure
credential store** — Windows Credential Manager on Windows (the same vault
Windows uses for its own logins) — never in a plain text file.

## Download & run (Android)

1. On the [Releases](../../releases) page, download the latest `.apk`.
2. Open it on your phone. Android will ask you to allow installing from this
   source — accept (Settings → "Install unknown apps" for your browser/files app).
3. Open the app, fill in **Settings** (same fields as above), and **Sync**.

On Android your credentials are stored in the **Android Keystore**. The app
isn't on the Play Store, so the "unknown source" prompt is expected.

## Run from source

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env    # optional: set IGPSYNC_DROPBOX_APP_KEY for Dropbox
uv run --env-file .env main.py
```

## Build the Windows executable

```bash
uv run flet build windows
```

The distributable lands in `build/windows/`. (Flet downloads the Flutter
toolchain on the first build.)

## Cutting a release

Releases are built automatically by GitHub Actions (`.github/workflows/release.yml`)
whenever you push a version tag. To publish a new version:

```bash
git tag v0.1.0      # pick the next version number
git push origin v0.1.0
```

The workflow builds the Windows app **and the Android APK** on clean runners and
attaches both (`igpsport-intervals-windows.zip` and an `.apk`) to a new GitHub
Release. Watch it run under the repo's **Actions** tab; the result appears under
**Releases**.

### Pre-releases (test a build before shipping)

Tag with a hyphen, e.g. `v0.3.0-rc1`, to publish a **pre-release**. It still
builds installable artifacts you can test on a device, but GitHub keeps the last
stable as **Latest** and the in-app update check ignores it — so users on the
stable version aren't notified. Once it's good, tag the final `v0.3.0`.

### Urgent hotfix while `master` has unreleased work

`master` only ever contains finished, merged PRs, so usually you can just merge
the fix and tag a patch. If `master` already has work you're not ready to ship,
branch the fix from the **last released tag** instead, so only the fix goes out:

```bash
# 1. Branch from the last released tag (NOT master):
git switch -c hotfix/v0.2.5 v0.2.4
# 2. Commit the fix on this branch, then push it:
git push -u origin hotfix/v0.2.5
# 3. Tag this branch's fix commit -> builds & publishes only the fix:
git tag v0.2.5 && git push origin v0.2.5
# 4. Open a PR from hotfix/v0.2.5 into master and merge it, so the fix is
#    also in master for future work (master is protected, so use a PR).
```

The tag points at the hotfix commit, so the build contains just the fix — none
of master's unreleased work. The merge into master (step 4) is separate and
happens *after* tagging.

## Roadmap

The app is built with [Flet](https://flet.dev), so the same Python code targets
desktop and Android today, with **iOS** (`flet build ipa`) possible from the same
code.

## Acknowledgements

This project builds on community work around iGPSPORT activity access and
syncing:

- [kamikadzem22/igpsport-unoffical-api](https://github.com/kamikadzem22/igpsport-unoffical-api)
  for documenting and exploring the unofficial iGPSPORT API.
- [simple4wan/ride-sync](https://github.com/simple4wan/ride-sync) for prior
  work on syncing ride activities between services.

This app is an independent project and is not affiliated with iGPSPORT,
intervals.icu, or the projects listed above.
