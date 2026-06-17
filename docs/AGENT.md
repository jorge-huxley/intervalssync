# Agent / headless sync

Use the `igpsync` CLI to sync cycling data between iGPSPORT and intervals.icu
without the GUI. It is designed for automation agents (e.g.
[Hermes](https://hermes-agent.nousresearch.com)) that need reliable upload
triggers for activities and/or planned workouts.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed
- This repository cloned locally
- Dependencies installed: `uv sync`

## User setup (human — not the agent)

Agents cannot write secrets. The **user** must add all three credentials to a
`**.env` file only** — never use `hermes config set` for the email or password.
Hermes routes `config set` by key name: only names ending in `_API_KEY` /
`_TOKEN` go to `.env`; everything else (including `IGPSYNC_IGP_USER` and
`IGPSYNC_IGP_PASSWORD`) goes to `config.yaml` **in plaintext**, which we do not use.

### Which `.env` file?

Hermes sets `HERMES_HOME` in subprocesses to the **active profile** directory.
The CLI reads `$HERMES_HOME/.env` automatically.


| Profile              | `.env` path                     | Auto-detected when       |
| -------------------- | ------------------------------- | ------------------------ |
| Default              | `~/.hermes/.env`                | `HERMES_HOME` unset      |
| Named (e.g. `coach`) | `~/.hermes/profiles/coach/.env` | agent runs under `coach` |


So for a named profile, put secrets in **that profile's** `.env`, not the
global `~/.hermes/.env` — otherwise `igpsync` won't find them.

### Setup commands

Replace paths and values. Example for the `coach` profile:

```bash
PROFILE_HOME=/root/.hermes/profiles/coach

echo 'IGPSYNC_IGP_USER=you@example.com' >> "$PROFILE_HOME/.env"
echo 'IGPSYNC_IGP_PASSWORD=your-igpsport-password' >> "$PROFILE_HOME/.env"
echo 'IGPSYNC_INTERVALS_API_KEY=your-intervals-api-key' >> "$PROFILE_HOME/.env"
chmod 600 "$PROFILE_HOME/.env"
```

Default profile (`hermes` with no named wrapper):

```bash
echo 'IGPSYNC_IGP_USER=you@example.com' >> ~/.hermes/.env
echo 'IGPSYNC_IGP_PASSWORD=your-igpsport-password' >> ~/.hermes/.env
echo 'IGPSYNC_INTERVALS_API_KEY=your-intervals-api-key' >> ~/.hermes/.env
chmod 600 ~/.hermes/.env
```

**intervals.icu API key:** intervals.icu → Settings → Developer.

If you previously ran `config set` for the user or password, remove those keys
from `config.yaml` — they belong only in `.env`.

Verify setup (from the repo, under the same profile the agent uses):

```bash
uv run igpsync check
```

Optional: pass `--env-file /path/to/.env` to override auto-detection.

## Agent invocation

### Activity sync (iGPSPORT → intervals.icu)

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

### Workout upload (intervals.icu → iGPSPORT)

```bash
uv run igpsync upload-workouts --json
```

Example success output:

```json
{
  "ok": true,
  "listed": 3,
  "uploaded": 1,
  "skipped": 1,
  "no_steps": 1,
  "failed": 0
}
```

Same progress/exit-code rules as activity sync.

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

Shared by all subcommands:

| Flag              | Purpose                        |
| ----------------- | ------------------------------ |
| `--env-file PATH` | Override secrets file location |
| `--json`          | Machine-readable JSON on stdout (progress on stderr) |

`sync` flags:

| Flag                   | Purpose                                        |
| ---------------------- | ---------------------------------------------- |
| `--max-activities N`   | Number of recent rides to process (default: 5) |
| `--force-resync`       | Re-upload even if already on intervals.icu     |
| `--activity-type TYPE` | Set intervals.icu sport after upload           |
| `--download-dir PATH`  | Directory for temporary `.fit` files           |
| `--keep-files`         | Do not delete `.fit` files after upload        |

`upload-workouts` flags:

| Flag                     | Purpose                                              |
| ------------------------ | ---------------------------------------------------- |
| `--workout-days-ahead N` | Calendar days to upload (default: 1 = today only)    |
| `--force-resync`         | Re-upload even if already on iGPSPORT                |


## Subcommands


| Command                    | Description                                                         |
| -------------------------- | ------------------------------------------------------------------- |
| `igpsync sync`             | Full pipeline: list → download → upload to intervals.icu            |
| `igpsync upload-workouts`  | Upload planned workouts from intervals.icu to iGPSPORT              |
| `igpsync check`            | Validate `.env` exists and has all three required keys (no network) |


## CLI config

Non-secret defaults are persisted in `config.json` under the `igpsync-cli`
app config directory (`platformdirs`). CLI flags override these per run.
Fields include `max_activities`, `workout_days_ahead`, `force_resync`,
`uploaded_workouts` (intervals.icu event id → iGPSPORT workoutId dedup map),
and activity-sync settings. Secrets never go in this file.


## What it does

### Activity sync (`sync`)

Same as the GUI one-click sync:

- Lists recent iGPSPORT activities
- Skips rides already on intervals.icu (unless `--force-resync`)
- Downloads `.fit` files and uploads to intervals.icu
- Deletes local `.fit` files after successful upload (unless `--keep-files`)
- Does **not** upload to Dropbox

### Workout upload (`upload-workouts`)

Same as the GUI **Upload workouts** button:

- Fetches planned cycling workouts from the intervals.icu calendar
- Skips workouts already on iGPSPORT (validates stored workout IDs against the live custom-workout list; re-uploads if deleted in the app)
- Skips non-cycling activity types (v1)
- Skips workouts with no structured steps (`no_steps` in JSON) — open the workout in intervals.icu first
- Persists the `uploaded_workouts` dedup map in CLI `config.json` after each run (stale entries pruned)

