# Contributing

Thanks for your interest in improving **iGPSPORT → intervals.icu**! This guide
covers how to set up the project, make a change, and open a pull request.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (manages Python and dependencies)
- Python 3.13 (uv will install it for you from `.python-version`)

## Setup

```bash
git clone https://github.com/jorge-huxley/igpsport-intervals.git
cd igpsport-intervals
uv sync          # installs runtime + dev dependencies into .venv
```

Run the app while developing:

```bash
uv run main.py          # launch the GUI
```

## Running the tests

```bash
uv run pytest
```

Tests are **offline** — they fake the network and never use real credentials, so
they're safe to run anywhere. Please add or update tests for any behavior you
change; the same suite runs in CI on every pull request and must pass before a
change can be merged.

## Project layout

The code is split into three layers so the app can later target mobile with
minimal change (see `CLAUDE.md` for the full picture):

- `src/igpsync/core.py` — pure sync logic (no UI, no side effects)
- `src/igpsync/config.py` + `secrets.py` — settings (JSON) and secrets (OS vault)
- `src/igpsync/gui/` — the Flet UI; `cli.py` / `main.py` — the headless entry

Keep new logic in `core` testable and UI-free; the GUI and CLI should stay thin.

## Working on the Dropbox upload (optional)

Dropbox is an optional, off-by-default upload target, so you only need to set
this up if you're working on that feature — without a key the Dropbox switch in
Settings stays disabled and the rest of the app works normally.

The app authenticates with Dropbox using the **PKCE** OAuth flow, which needs a
Dropbox **app key**. Releases get the key stamped in by CI from a repository
secret. For local development, **create your own Dropbox app** rather than
reusing the production one:

1. In the [Dropbox App Console](https://www.dropbox.com/developers/apps), create
   an app with **Scoped access** and **App folder** access, and enable the
   `account_info.read`, `files.metadata.read`, and `files.content.write` scopes.
2. Copy the app's **App key**.
3. Copy `.env.example` to `.env`, set `IGPSYNC_DROPBOX_APP_KEY` to your key, and
   run with uv's `--env-file` flag (which loads the file into the environment):

   ```bash
   cp .env.example .env        # then edit .env and paste your app key
   uv run --env-file .env main.py
   ```

`.env` is gitignored. The app key for a PKCE public client isn't a secret (it
ships inside released builds), but use your own for development so you don't
share the production app's rate limit.

## Making a change

1. **Fork** the repository (or create a branch if you're a collaborator).
2. Create a topic branch: `git switch -c feat/short-description`.
3. Make your change and add tests.
4. Run `uv run pytest` and make sure everything passes.
5. Commit using **[Conventional Commits](https://www.conventionalcommits.org/)**,
   e.g. `feat(gui): add gravel ride to type list` or `fix(core): handle empty
   activity list`. Common types: `feat`, `fix`, `docs`, `test`, `refactor`,
   `chore`, `ci`.
6. Push your branch and **open a pull request** against `master`. Describe what
   changed and why.

## Things to keep in mind

- **Never commit secrets.** Credentials live in the OS-native credential vault
  (Windows Credential Manager / macOS Keychain / Android Keystore / Linux
  libsecret) via the `flet-secure-storage` service — never in a file. Don't add
  real API keys, passwords, or personal data to the repo, tests, or commits.
- The Flet API changes between versions — verify control arguments against the
  installed version (currently 0.85.x) rather than older tutorials.

## Releases (maintainers)

Releases are built by GitHub Actions when a version tag is pushed:

```bash
git tag v0.2.0
git push origin v0.2.0
```

This builds the Windows app and attaches it to a new GitHub Release. See
`.github/workflows/release.yml`.
