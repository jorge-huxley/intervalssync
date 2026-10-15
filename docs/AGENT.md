# Agent / headless sync

Use the `intervalssync` CLI (headless companion to **Intervals Sync**) to sync
cycling activities to intervals.icu without the GUI. Sources: **iGPSPORT**
(default) or **Bryton Active** (`--source bryton`).
Also uploads planned workouts from intervals.icu to **iGPSPORT** or **Bryton Active**.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed

No repository clone or virtual environment is needed. `uvx` downloads the
latest stable `intervalssync` release from PyPI into an isolated environment.
The explicit `@latest` refreshes uv's cached package metadata on every run.

## User setup (human — not the agent)

Agents cannot write secrets. The **user** must add credentials to a **`.env` file
only** — never use `hermes config set` for email or password (those end up in
`config.yaml` in plaintext).

### iGPSPORT sync

```bash
echo 'INTERVALSSYNC_IGPSPORT_USER=you@example.com' >> ~/.hermes/.env
echo 'INTERVALSSYNC_IGPSPORT_PASSWORD=your-password' >> ~/.hermes/.env
echo 'INTERVALSSYNC_INTERVALS_API_KEY=your-intervals-api-key' >> ~/.hermes/.env
chmod 600 ~/.hermes/.env
```

For **China-region** accounts ([app.igpsport.cn](https://app.igpsport.cn/login)), use your phone number as the username and add:

```bash
echo 'INTERVALSSYNC_IGPSPORT_REGION=china' >> ~/.hermes/.env
```

### Bryton sync

```bash
echo 'INTERVALSSYNC_BRYTON_EMAIL=you@example.com' >> ~/.hermes/.env
echo 'INTERVALSSYNC_BRYTON_PASSWORD=your-password' >> ~/.hermes/.env
echo 'INTERVALSSYNC_INTERVALS_API_KEY=your-intervals-api-key' >> ~/.hermes/.env
chmod 600 ~/.hermes/.env
```

For a named Hermes profile, use `$HERMES_HOME/.env` (that profile's directory).

**intervals.icu API key:** intervals.icu → Settings → Developer.

Verify:

```bash
uvx --python 3.13 intervalssync@latest check                   # iGPSPORT keys
uvx --python 3.13 intervalssync@latest check --source bryton   # Bryton keys
```

Optional: `--env-file /path/to/.env` on the **intervalssync** command (e.g.
`uvx --python 3.13 intervalssync@latest sync-zones --env-file .env`).

Check which release the agent will run:

```bash
uvx --python 3.13 intervalssync@latest --version
```

## Agent invocation

### Activity sync

```bash
uvx --python 3.13 intervalssync@latest sync --json                   # iGPSPORT
uvx --python 3.13 intervalssync@latest sync --source bryton --json   # Bryton Active
```

- **Progress** on **stderr**; **result** JSON on **stdout**.
- **Exit code:** `0` success · `1` sync error · `2` missing credentials

iGPSPORT success example:

```json
{
  "ok": true,
  "source": "igpsport",
  "listed": 5,
  "uploaded": 2,
  "skipped": 3,
  "failed": 0,
  "downloaded": 2,
  "activities": [{"ride_id": 123, "title": "Morning ride", "start_time": "2026-06-15 08:00:00"}]
}
```

Bryton success uses `"source": "bryton"` and `activity_id` instead of `ride_id`.

### Workout upload (intervals.icu → iGPSPORT or Bryton)

```bash
uvx --python 3.13 intervalssync@latest upload-workouts --json                   # iGPSPORT
uvx --python 3.13 intervalssync@latest upload-workouts --source bryton --json   # Bryton Active
```

Requires credentials for the chosen target. Same exit-code rules.

### Zone sync (intervals.icu → iGPSPORT profile)

```bash
uvx --python 3.13 intervalssync@latest sync-zones --env-file .env --json
```

- **iGPSPORT-only** (no `--source` flag)
- Reads FTP, LTHR, max HR, power zones, and HR zones from intervals.icu `sport-settings/Ride` (override with `--sport`), plus athlete weight (`icu_weight`) rounded to whole kg
- Writes thresholds/zones via `UpdatePersonalIntervalInfo`, and weight via `User/UpdatePersonalUserInfo` (the endpoint the app profile editor uses)
- Progress on **stderr**; result JSON on **stdout**; same exit codes as other commands

Success example:

```json
{
  "ok": true,
  "source": "igpsport",
  "before": {
    "ftp": 240,
    "lthr": 153,
    "mhr": 193,
    "weight": 79.0,
    "power_zones": "0-132 | 132-180 | …",
    "hr_zones": "0-120 | …"
  },
  "ftp": 242,
  "lthr": 176,
  "mhr": 193,
  "weight": 76.0,
  "power_zones": "0-133 | 133-182 | …",
  "hr_zones": "0-120 | 120-146 | …",
  "after": {
    "ftp": 242,
    "lthr": 176,
    "mhr": 193,
    "weight": 76.0,
    "power_zones": "0-133 | 133-182 | …",
    "hr_zones": "0-120 | 120-146 | …"
  }
}
```

## Optional flags

| Flag | Purpose |
|------|---------|
| `--source {igpsport,bryton}` | Activity source or workout upload target (default: igpsport) |
| `--env-file PATH` | Override secrets file |
| `--json` | JSON on stdout |
| `--sport TYPE` | intervals.icu sport-settings key for `sync-zones` (default: Ride) |

`sync` flags: `--max-activities`, `--force-resync`, `--activity-type`, `--download-dir`, `--keep-files`.

## Subcommands

| Command | Description |
|---------|-------------|
| `intervalssync sync` | Download recent rides → upload to intervals.icu |
| `intervalssync upload-workouts` | Planned workouts → iGPSPORT or Bryton (`--source`) |
| `intervalssync sync-zones` | Push thresholds + zones from intervals.icu → iGPSPORT profile |
| `intervalssync check` | Validate `.env` keys (no network) |

`@latest` means the newest stable release published to PyPI, not the newest
commit on `master`. Maintainers must cut a new stable tag before agents receive
a merged fix.

## CLI config

Non-secret defaults in `intervalssync-cli` `config.json` (`platformdirs`). Secrets never go there.

## What it does

### Activity sync

- **iGPSPORT:** list → FIT URL → download → upload (`igpsport_{ride_id}` external_id).
- **Bryton:** DDP login → activity list → `GET /api/activity?id=…` FIT → upload (`bryton_{id}` external_id).
- Skips already on intervals.icu unless `--force-resync`.
- **Dropbox** is GUI-only (Settings → connect Dropbox, enable upload). iGPSPORT
  uses `ride-0-YYYY-MM-DD-HH-MM-SS.fit` or `igpsport_{id}.fit`; Bryton uses
  `YYMMDDHHMMSS.fit` or `bryton_{id}.fit`.

### Workout upload

Same as GUI **Upload to iGPSPORT** / **Upload to Bryton** — intervals.icu calendar → custom workouts on the chosen device platform.

For iGPSPORT, CLI and GUI keep the existing `uploaded_workouts` event-ID mapping
authoritative. Per-event `workout_export_state` stores export fingerprints and
verification metadata bound to that mapped remote ID. Changed exports for the
same event update the same remote workout; verified unchanged exports skip writes.
Legacy mappings without metadata are updated and verified once. If a remote workout is
manually deleted while its source remains inside the configured upload window,
the next run recreates the latest version. Outside that window, missing remote
workouts are not recreated. No automatic remote deletion is implemented.

Matching uses only the exact Intervals event ID. A replacement event with a new
ID is a new workout; there is no provider matching, date fallback, or cross-event
rebinding. Incomplete remote or calendar observations fail closed; source events
without structured steps retain their mappings. iGPSPORT custom workouts are a
list, not a synchronized execution-date calendar.

Add `[skip-igp]` to the Intervals event name or description to suppress create,
update, and recreation, including `--force-resync`. Removing the marker resumes
sync. `[ignore-igp]` and `[delete-igp]` are ordinary text.

The event description takes precedence over the nested workout description and
is limited to 500 characters. Warmup/cooldown/rest classification follows explicit
step metadata rather than position or power.

The exporter preserves cadence as native `secondaryIntensityTarget` alongside
primary power or HR. It honors the workout's explicit `POWER` or `HR` selection,
uses native target units, and preserves time, distance, repetition, and open/lap
lengths. The legacy `cadenceTarget` field is not emitted. Secondary speed and
HR/power combinations, ramps, freeride, maximum-effort steps, calorie lengths,
and malformed repetitions are unsupported and fail before the workout is written.

Every accepted create/update is fetched with `GetWorkOutDetail` and compared
against the expected executable structure, including primary and secondary
targets. An HTTP success alone is not a verified upload. CLI and GUI checkpoint
the accepted remote ID as pending before read-back, so a failed verifier does
not lose the mapping and trigger duplicate creation. Pending records do not
acquire a confirmed export fingerprint until verification succeeds.

JSON includes `uploaded`, `updated`, `recreated`, `skipped`,
`no_steps`, `description_truncated`, `unsupported`, `verification_failed`,
`failed`, `uploaded_map`, and `synced_map`. Unsupported or unverified exports
increment `failed`. Failures produce a nonzero CLI exit code.

### Zone sync

Reads FTP, LTHR, max HR, power/HR zones, and weight from intervals.icu and writes them to the iGPSPORT profile (CLI only for now).
