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

Headless sync and agent integration: [docs/AGENT.md](docs/AGENT.md).

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
