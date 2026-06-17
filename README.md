# iGPSPORT → intervals.icu

[![License: MIT](https://img.shields.io/github/license/jorge-huxley/igpsport-intervals)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/downloads/)
[![Tests](https://github.com/jorge-huxley/igpsport-intervals/actions/workflows/test.yml/badge.svg)](https://github.com/jorge-huxley/igpsport-intervals/actions/workflows/test.yml)
[![GitHub release](https://img.shields.io/github/v/release/jorge-huxley/igpsport-intervals)](https://github.com/jorge-huxley/igpsport-intervals/releases)
[![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Android-lightgrey)](#download--run-windows)
[![Stars](https://img.shields.io/github/stars/jorge-huxley/igpsport-intervals?label=stars)](https://github.com/jorge-huxley/igpsport-intervals/stargazers)

A small, friendly app that syncs your cycling activities between **iGPSPORT** and
**intervals.icu**. It's built for non-technical riders — no command line, no config
files: enter your credentials once, press **Sync**, and your latest rides land on
intervals.icu. You can also push planned workouts the other way. Free and open
source, for **Windows** and **Android**.

## Features

- Lists your recent iGPSPORT activities and uploads the original `.fit` files to intervals.icu
- **Upload workouts** — push planned cycling workouts from your intervals.icu calendar to iGPSPORT custom workouts (sync to your head unit from the iGPSPORT app)
- **Skips activities already uploaded** so re-running is safe — with an optional *force re-sync*
- Lets you choose how many recent activities to process
- **Workout upload window** in Settings — how many calendar days to upload (default: today only)
- **Sets the intervals.icu sport type** after upload (e.g. Mountain Bike Ride / Gravel Ride) — iGPSPORT exports everything as a generic "Ride"
- Optionally deletes the local `.fit` files after a successful upload
- Stores your credentials in the **OS secure vault** (Windows Credential Manager / Android Keystore), never in a file
- Lets you know when a newer version is available
- **Headless CLI** — activity sync and workout upload from the terminal, with JSON output and exit codes for automation and AI agents (see [CLI & automation](#cli--automation-ai-agents))

> Prefer the terminal, or want to help out? It's open source (Python + [Flet](https://flet.dev), MIT) — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Download & run (Windows)

1. Go to the [Releases](../../releases) page and download the latest `.zip`.
2. Unzip it anywhere and double-click the app (e.g. `igpsync.exe`).
3. On first launch, open **Settings** and enter:
   - your iGPSPORT **email** and **password**
   - your intervals.icu **API key** (intervals.icu → Settings → Developer)
4. Click **Save**, then go back and press **Sync activities** (or **Upload workouts** for planned sessions on your intervals.icu calendar).

Your password and API key are stored in your operating system's **secure
credential store** — Windows Credential Manager on Windows (the same vault
Windows uses for its own logins) — never in a plain text file.

## Download & run (Android)

1. On the [Releases](../../releases) page, download the latest `.apk`.
2. Open it on your phone. Android will ask you to allow installing from this
   source — accept (Settings → "Install unknown apps" for your browser/files app).
3. Open the app, fill in **Settings** (same fields as above), then **Sync activities** or **Upload workouts**.

On Android your credentials are stored in the **Android Keystore**. The app
isn't on the Play Store, so the "unknown source" prompt is expected.

## CLI & automation (AI agents)

Headless `igpsync` CLI for scripts and AI agents ([Hermes](https://hermes-agent.nousresearch.com), [OpenClaw](https://openclaw.ai/)) — sync activities to intervals.icu, upload planned workouts to iGPSPORT, JSON on stdout, credentials in `.env`. Setup, flags, and invocation: [Agent / headless sync](docs/AGENT.md).

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
