"""Headless CLI for syncing iGPSPORT activities to intervals.icu.

Designed for agent use (e.g. Hermes): credentials are read from the profile
.env file; progress goes to stderr; structured results go to stdout with --json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import cli_config as cli_config_module
from .cli_env import CliConfigError, load_credentials, resolve_env_path
from .core import SyncConfig, SyncError, SyncResult, sync

EXIT_OK = 0
EXIT_SYNC_ERROR = 1
EXIT_CONFIG_ERROR = 2


def _build_sync_config(
    credentials,
    config: cli_config_module.CliConfig,
    *,
    max_activities: int | None,
    force_resync: bool | None,
    activity_type: str | None,
    download_dir: str | None,
    delete_after_upload: bool | None,
) -> SyncConfig:
    return SyncConfig(
        igp_user=credentials.igp_user,
        igp_password=credentials.igp_password,
        intervals_api_key=credentials.intervals_api_key,
        max_activities=max_activities if max_activities is not None else config.max_activities,
        download_dir=Path(download_dir or config.download_dir),
        delete_after_upload=(
            delete_after_upload if delete_after_upload is not None else config.delete_after_upload
        ),
        force_resync=force_resync if force_resync is not None else config.force_resync,
        activity_type=activity_type if activity_type is not None else config.activity_type,
        list_activities=True,
        get_download_url=True,
        download_fit=True,
        upload_intervals=True,
        upload_dropbox=False,
    )


def _result_payload(result: SyncResult, *, ok: bool, error: str | None = None) -> dict:
    payload = {
        "ok": ok,
        "listed": result.listed,
        "uploaded": result.uploaded,
        "skipped": result.skipped,
        "failed": result.failed,
        "downloaded": result.downloaded,
        "activities": [
            {
                "ride_id": act.ride_id,
                "title": act.title,
                "start_time": act.start_time,
            }
            for act in result.activities
        ],
    }
    if error is not None:
        payload["error"] = error
    return payload


def _emit_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2))


def _emit_text_summary(result: SyncResult) -> None:
    print(
        f"Done — uploaded {result.uploaded}, "
        f"downloaded {result.downloaded}, "
        f"skipped {result.skipped}, "
        f"failed {result.failed}."
    )


def cmd_check(args: argparse.Namespace) -> int:
    config = cli_config_module.load()
    try:
        env_path = resolve_env_path(
            env_file=Path(args.env_file) if args.env_file else None,
            config_env_file=config.env_file or None,
        )
        load_credentials(env_path)
    except CliConfigError as exc:
        if args.json:
            _emit_json({"ok": False, "error": str(exc)})
        else:
            print(exc, file=sys.stderr)
        return EXIT_CONFIG_ERROR

    if args.json:
        _emit_json({"ok": True, "env_file": str(env_path)})
    else:
        print(f"Credentials OK ({env_path})")
    return EXIT_OK


def cmd_sync(args: argparse.Namespace) -> int:
    config = cli_config_module.load()
    use_json = args.json

    try:
        env_path = resolve_env_path(
            env_file=Path(args.env_file) if args.env_file else None,
            config_env_file=config.env_file or None,
        )
        credentials = load_credentials(env_path)
    except CliConfigError as exc:
        if use_json:
            _emit_json({"ok": False, "error": str(exc)})
        else:
            print(exc, file=sys.stderr)
        return EXIT_CONFIG_ERROR

    delete_after_upload = False if args.keep_files else None

    sync_config = _build_sync_config(
        credentials,
        config,
        max_activities=args.max_activities,
        force_resync=True if args.force_resync else None,
        activity_type=args.activity_type,
        download_dir=args.download_dir,
        delete_after_upload=delete_after_upload,
    )

    def progress(message: str) -> None:
        print(message, file=sys.stderr)

    try:
        result = sync(sync_config, progress=progress)
    except SyncError as exc:
        if use_json:
            _emit_json(_result_payload(SyncResult(), ok=False, error=str(exc)))
        else:
            print(f"✗ {exc}", file=sys.stderr)
        return EXIT_SYNC_ERROR
    except Exception as exc:  # noqa: BLE001 — surface unexpected failures to agents
        if use_json:
            _emit_json(_result_payload(SyncResult(), ok=False, error=str(exc)))
        else:
            print(f"✗ Unexpected error: {exc}", file=sys.stderr)
        return EXIT_SYNC_ERROR

    ok = result.failed == 0
    if use_json:
        _emit_json(_result_payload(result, ok=ok))
    else:
        _emit_text_summary(result)

    return EXIT_OK if ok else EXIT_SYNC_ERROR


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--env-file",
        metavar="PATH",
        help="Override path to the secrets .env file.",
    )
    common.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON on stdout (progress stays on stderr).",
    )

    parser = argparse.ArgumentParser(
        prog="igpsync",
        description="Sync cycling activities from iGPSPORT to intervals.icu.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    check_parser = subparsers.add_parser(
        "check",
        parents=[common],
        help="Validate credentials in the .env file (no network).",
    )
    check_parser.set_defaults(func=cmd_check)

    sync_parser = subparsers.add_parser(
        "sync",
        parents=[common],
        help="Download recent rides from iGPSPORT and upload to intervals.icu.",
    )
    sync_parser.add_argument(
        "--max-activities",
        type=int,
        metavar="N",
        help="Number of recent activities to process (default: from cli config).",
    )
    sync_parser.add_argument(
        "--force-resync",
        action="store_true",
        help="Re-upload activities even if already on intervals.icu.",
    )
    sync_parser.add_argument(
        "--activity-type",
        metavar="TYPE",
        help='intervals.icu sport to set after upload (e.g. "Mountain Bike Ride").',
    )
    sync_parser.add_argument(
        "--download-dir",
        metavar="PATH",
        help="Directory for temporary .fit files.",
    )
    sync_parser.add_argument(
        "--keep-files",
        action="store_true",
        help="Keep .fit files after upload instead of deleting them.",
    )
    sync_parser.set_defaults(func=cmd_sync)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
