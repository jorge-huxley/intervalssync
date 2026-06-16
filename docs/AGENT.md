# Agent / headless sync

Use the `igpsync` CLI to upload recent rides from iGPSPORT to intervals.icu
without the GUI. It is designed for automation agents (e.g.
[Hermes](https://hermes-agent.nousresearch.com)) that already detect new
activities and only need a reliable upload trigger.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed
- This repository cloned locally
- Dependencies installed: `uv sync`

## User setup (human — not the agent)

Agents cannot write secrets. The **user** must configure credentials once in
their Hermes profile. Replace `{profile}` with the Hermes profile wrapper name
(e.g. `hermes` for the default profile, or `coder` for a named profile):

```bash
{profile} config set IGPSYNC_IGP_USER you@example.com
{profile} config set IGPSYNC_IGP_PASSWORD your-igpsport-password
{profile} config set IGPSYNC_INTERVALS_API_KEY your-intervals-api-key
```

Hermes stores these in `{HERMES_HOME}/.env`. The CLI reads that file
automatically when run under Hermes (via the `HERMES_HOME` environment
variable). No skill or `env_passthrough` configuration is required.

**intervals.icu API key:** intervals.icu → Settings → Developer.

Verify setup:

```bash
uv run igpsync check
```

Optional: override the secrets file path in CLI config
(`platformdirs.user_config_dir("igpsync-cli")/config.json`) with an `env_file`
field, or pass `--env-file PATH` per invocation.

## Agent invocation

From the repository root:

```bash
uv run igpsync sync --json
```

- **Progress** is written to **stderr** (safe to ignore or log).
- **Result** is a single JSON object on **stdout**.
- **Exit code:** `0` success · `1` sync error or failures · `2` missing credentials

Example success output:

```json
{
  "ok": true,
  "listed": 5,
  "uploaded": 2,
  "skipped": 3,
  "failed": 0,
  "downloaded": 2,
  "activities": [
    {
      "ride_id": 123,
      "title": "Morning ride",
      "start_time": "2026-06-15 08:00:00"
    }
  ]
}
```

Example credential error:

```json
{
  "ok": false,
  "error": "Missing required keys in ..."
}
```

The agent should parse stdout JSON and check the exit code. It must **not**
handle or write secrets.

## Optional flags

| Flag | Purpose |
|------|---------|
| `--env-file PATH` | Override secrets file location |
| `--max-activities N` | Number of recent rides to process (default: 5) |
| `--force-resync` | Re-upload even if already on intervals.icu |
| `--activity-type TYPE` | Set intervals.icu sport after upload |
| `--download-dir PATH` | Directory for temporary `.fit` files |
| `--keep-files` | Do not delete `.fit` files after upload |

## Subcommands

| Command | Description |
|---------|-------------|
| `igpsync sync` | Full pipeline: list → download → upload to intervals.icu |
| `igpsync check` | Validate `.env` exists and has all three required keys (no network) |

## What it does

Same as the GUI one-click sync:

- Lists recent iGPSPORT activities
- Skips rides already on intervals.icu (unless `--force-resync`)
- Downloads `.fit` files and uploads to intervals.icu
- Deletes local `.fit` files after successful upload (unless `--keep-files`)
- Does **not** upload to Dropbox
