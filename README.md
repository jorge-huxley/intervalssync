# iGPSPORT → intervals.icu

A small, friendly app that downloads your cycling activities from **iGPSPORT** and
uploads them to **intervals.icu**. No command line, no config files — just enter
your details once and click **Sync**.

## Download & run (Windows)

1. Go to the [Releases](../../releases) page and download the latest `.zip`.
2. Unzip it anywhere and double-click the app (e.g. `igpsync.exe`).
3. On first launch, open **Settings** and enter:
   - your iGPSPORT **email** and **password**
   - your intervals.icu **API key** (intervals.icu → Settings → Developer)
4. Click **Save**, then go back and press **Sync activities**.

Your password and API key are stored in **Windows Credential Manager** (the same
secure vault Windows uses for its own logins) — never in a plain text file.

## Run from source

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run main.py          # launch the app
uv run main.py --cli    # headless sync (for automation)
```

## Build the Windows executable

```bash
uv run flet build windows
```

The distributable lands in `build/windows/`. Zip that folder and attach it to a
GitHub Release. (Flet downloads the Flutter toolchain on the first build.)

## Roadmap

The app is built with [Flet](https://flet.dev), so the same Python code can later
be packaged for **Android** (`flet build apk`) and **iOS** (`flet build ipa`).
