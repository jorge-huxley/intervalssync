# AGENTS.md

See `CLAUDE.md` for architecture, `README.md` for an overview, `CONTRIBUTING.md`
for contributor setup, and `docs/AGENT.md` for the headless CLI. The commands
below live in those files; this section only adds non-obvious cloud caveats.

## Cursor Cloud specific instructions

This is a Python 3.13 project managed by [uv](https://docs.astral.sh/uv/).
Dependencies are refreshed automatically by the startup update script (`uv sync`).
`uv` is installed at `~/.local/bin` and put on `PATH` via `~/.bashrc`.

### Services

- **Tests** (offline, no network): `uv run pytest`. Standard command; see `CLAUDE.md`.
- **CLI** (`intervalssync`): headless. `uv run intervalssync check` validates
  credentials with no network. Full commands in `docs/AGENT.md`. Exit codes:
  `0` ok, `1` sync error, `2` missing credentials.
- **GUI** (`intervalssync-gui`): a Flet app. See below — it needs a special
  run mode on Linux.

### Running the GUI on Linux (non-obvious)

The GUI targets Windows/Android as a native Flet desktop app. On this Linux VM
the native desktop client does **not** work: `flet-secure-storage` /
`flet-permission-handler` raise `FletUnsupportedPlatformException`
("only supported on Android, iOS, Windows, and Web platforms"), and the desktop
Flutter client also needs GL/GTK system libraries.

Run it as a **web app** instead (Web is a supported platform, so the vault +
permission services load). No system graphics libraries are needed in web mode:

```bash
FLET_FORCE_WEB_SERVER=true FLET_SERVER_PORT=8550 FLET_SERVER_IP=0.0.0.0 uv run intervalssync-gui
```

Then open `http://localhost:8550/`. The first web launch auto-installs the
`flet-web` extra (fastapi/uvicorn/etc.) into the venv, so allow a few seconds.
In web mode the OS secure vault is emulated in the browser, which is fine for
development and testing.

### Notes

- No linter/formatter is configured; CI (`.github/workflows/test.yml`) only runs
  `uv run pytest`.
- Credentials for the CLI come from a `.env` file (see `.env.example` /
  `docs/AGENT.md`); pass it with `--env-file PATH` on the `intervalssync`
  subcommand (not as a `uv run` flag). Never commit real secrets.
