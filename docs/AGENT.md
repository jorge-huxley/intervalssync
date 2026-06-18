# Agent / headless sync

Use the `intervalssync` CLI to sync cycling activities to intervals.icu without
the GUI. Sources: **iGPSPORT** (default) or **Bryton Active** (`--source bryton`).
Also uploads planned workouts from intervals.icu to **iGPSPORT** or **Bryton Active**.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed
- This repository cloned locally
- Dependencies installed: `uv sync`

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
uv run intervalssync check                    # iGPSPORT keys
uv run intervalssync check --source bryton      # Bryton keys
```

Optional: `--env-file /path/to/.env`.

## Agent invocation

### Activity sync

```bash
uv run intervalssync sync --json                        # iGPSPORT
uv run intervalssync sync --source bryton --json        # Bryton Active
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
uv run intervalssync upload-workouts --json                        # iGPSPORT
uv run intervalssync upload-workouts --source bryton --json        # Bryton Active
```

Requires credentials for the chosen target. Same exit-code rules.

## Optional flags

| Flag | Purpose |
|------|---------|
| `--source {igpsport,bryton}` | Activity source or workout upload target (default: igpsport) |
| `--env-file PATH` | Override secrets file |
| `--json` | JSON on stdout |

`sync` flags: `--max-activities`, `--force-resync`, `--activity-type`, `--download-dir`, `--keep-files`.

## Subcommands

| Command | Description |
|---------|-------------|
| `intervalssync sync` | Download recent rides → upload to intervals.icu |
| `intervalssync upload-workouts` | Planned workouts → iGPSPORT or Bryton (`--source`) |
| `intervalssync check` | Validate `.env` keys (no network) |

## CLI config

Non-secret defaults in `intervalssync-cli` `config.json` (`platformdirs`). Secrets never go there.

## What it does

### Activity sync

- **iGPSPORT:** list → FIT URL → download → upload (`igpsport_{ride_id}` external_id).
- **Bryton:** DDP login → activity list → `GET /api/activity?id=…` FIT → upload (`bryton_{id}` external_id).
- Skips already on intervals.icu unless `--force-resync`.

### Workout upload

Same as GUI **Upload to iGPSPORT** / **Upload to Bryton** — intervals.icu calendar → custom workouts on the chosen device platform.
