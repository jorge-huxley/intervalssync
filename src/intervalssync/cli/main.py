"""Headless CLI for syncing activities to intervals.icu.

Supports multiple activity sources (iGPSPORT, Bryton). Credentials are read
from a .env file; progress goes to stderr; structured results go to stdout with
--json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..bryton.core import SyncConfig as BrytonSyncConfig
from ..bryton.core import SyncResult as BrytonSyncResult
from ..bryton.core import sync as bryton_sync
from ..bryton.exceptions import BrytonSyncError
from ..igpsport.core import SyncConfig as IgpSyncConfig
from ..igpsport.core import SyncError as IgpSyncError
from ..igpsport.core import SyncResult as IgpSyncResult
from ..igpsport.core import sync as igpsport_sync
from ..igpsport.profile_sync import (
    ProfileSyncConfig,
    ProfileSyncResult,
    result_payload as profile_sync_result_payload,
    sync_profile_zones,
)
from ..bryton.workout import (
    BrytonWorkoutUploadConfig,
    BrytonWorkoutUploadResult,
    apply_uploaded_bryton_workout_map,
    upload_workouts as bryton_upload_workouts,
)
from ..igpsport.workout import (
    WorkoutUploadConfig,
    WorkoutUploadResult,
    apply_uploaded_workout_map,
    upload_workouts,
)
from . import config as cli_config_module
from .env import ActivitySource, CliConfigError, load_credentials, resolve_env_path

EXIT_OK = 0
EXIT_SYNC_ERROR = 1
EXIT_CONFIG_ERROR = 2


def _build_igpsport_sync_config(
    credentials,
    config: cli_config_module.CliConfig,
    *,
    max_activities: int | None,
    force_resync: bool | None,
    activity_type: str | None,
    download_dir: str | None,
    delete_after_upload: bool | None,
) -> IgpSyncConfig:
    return IgpSyncConfig(
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


def _build_bryton_sync_config(
    credentials,
    config: cli_config_module.CliConfig,
    *,
    max_activities: int | None,
    force_resync: bool | None,
    activity_type: str | None,
    download_dir: str | None,
    delete_after_upload: bool | None,
) -> BrytonSyncConfig:
    return BrytonSyncConfig(
        bryton_email=credentials.bryton_email,
        bryton_password=credentials.bryton_password,
        intervals_api_key=credentials.intervals_api_key,
        max_activities=max_activities if max_activities is not None else config.max_activities,
        download_dir=Path(download_dir or config.download_dir),
        delete_after_upload=(
            delete_after_upload if delete_after_upload is not None else config.delete_after_upload
        ),
        force_resync=force_resync if force_resync is not None else config.force_resync,
        activity_type=activity_type if activity_type is not None else config.activity_type,
        list_activities=True,
        download_fit=True,
        upload_intervals=True,
    )


def _igpsport_result_payload(result: IgpSyncResult, *, ok: bool, error: str | None = None) -> dict:
    payload = {
        "ok": ok,
        "source": "igpsport",
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


def _bryton_result_payload(result: BrytonSyncResult, *, ok: bool, error: str | None = None) -> dict:
    payload = {
        "ok": ok,
        "source": "bryton",
        "listed": result.listed,
        "uploaded": result.uploaded,
        "skipped": result.skipped,
        "failed": result.failed,
        "downloaded": result.downloaded,
        "activities": [
            {
                "activity_id": act.activity_id,
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


def _emit_igpsport_text_summary(result: IgpSyncResult) -> None:
    print(
        f"Done — uploaded {result.uploaded}, "
        f"downloaded {result.downloaded}, "
        f"skipped {result.skipped}, "
        f"failed {result.failed}."
    )


def _emit_bryton_text_summary(result: BrytonSyncResult) -> None:
    print(
        f"Done — uploaded {result.uploaded}, "
        f"downloaded {result.downloaded}, "
        f"skipped {result.skipped}, "
        f"failed {result.failed}."
    )


def _build_workout_upload_config(
    credentials,
    config: cli_config_module.CliConfig,
    *,
    workout_days_ahead: int | None,
    force_resync: bool | None,
) -> WorkoutUploadConfig:
    return WorkoutUploadConfig(
        igp_user=credentials.igp_user,
        igp_password=credentials.igp_password,
        intervals_api_key=credentials.intervals_api_key,
        workout_days_ahead=(
            workout_days_ahead if workout_days_ahead is not None else config.workout_days_ahead
        ),
        uploaded_workouts=dict(config.uploaded_workouts),
        force_resync=force_resync if force_resync is not None else config.force_resync,
    )


def _build_bryton_workout_upload_config(
    credentials,
    config: cli_config_module.CliConfig,
    *,
    workout_days_ahead: int | None,
    force_resync: bool | None,
) -> BrytonWorkoutUploadConfig:
    return BrytonWorkoutUploadConfig(
        bryton_email=credentials.bryton_email,
        bryton_password=credentials.bryton_password,
        intervals_api_key=credentials.intervals_api_key,
        workout_days_ahead=(
            workout_days_ahead if workout_days_ahead is not None else config.workout_days_ahead
        ),
        uploaded_workouts=dict(config.uploaded_bryton_workouts),
        force_resync=force_resync if force_resync is not None else config.force_resync,
    )


def _workout_result_payload(
    result: WorkoutUploadResult | BrytonWorkoutUploadResult,
    *,
    ok: bool,
    source: str = "igpsport",
    error: str | None = None,
) -> dict:
    payload = {
        "ok": ok,
        "source": source,
        "listed": result.listed,
        "uploaded": result.uploaded,
        "skipped": result.skipped,
        "failed": result.failed,
        "no_steps": result.no_steps,
    }
    if error is not None:
        payload["error"] = error
    return payload


def _emit_workout_text_summary(result: WorkoutUploadResult | BrytonWorkoutUploadResult) -> None:
    print(
        f"Done — uploaded {result.uploaded}, "
        f"skipped {result.skipped}, "
        f"no steps {result.no_steps}, "
        f"failed {result.failed}."
    )


def _source_from_args(args: argparse.Namespace) -> ActivitySource:
    return args.source


def cmd_check(args: argparse.Namespace) -> int:
    config = cli_config_module.load()
    source = _source_from_args(args)
    try:
        env_path = resolve_env_path(
            env_file=Path(args.env_file) if args.env_file else None,
            config_env_file=config.env_file or None,
        )
        load_credentials(env_path, source=source)
    except CliConfigError as exc:
        if args.json:
            _emit_json({"ok": False, "source": source, "error": str(exc)})
        else:
            print(exc, file=sys.stderr)
        return EXIT_CONFIG_ERROR

    if args.json:
        _emit_json({"ok": True, "source": source, "env_file": str(env_path)})
    else:
        print(f"Credentials OK for {source} ({env_path})")
    return EXIT_OK


def cmd_sync(args: argparse.Namespace) -> int:
    config = cli_config_module.load()
    use_json = args.json
    source = _source_from_args(args)

    try:
        env_path = resolve_env_path(
            env_file=Path(args.env_file) if args.env_file else None,
            config_env_file=config.env_file or None,
        )
        credentials = load_credentials(env_path, source=source)
    except CliConfigError as exc:
        if use_json:
            _emit_json({"ok": False, "source": source, "error": str(exc)})
        else:
            print(exc, file=sys.stderr)
        return EXIT_CONFIG_ERROR

    delete_after_upload = False if args.keep_files else None

    def progress(message: str) -> None:
        print(message, file=sys.stderr)

    if source == "bryton":
        sync_config = _build_bryton_sync_config(
            credentials,
            config,
            max_activities=args.max_activities,
            force_resync=True if args.force_resync else None,
            activity_type=args.activity_type,
            download_dir=args.download_dir,
            delete_after_upload=delete_after_upload,
        )
        try:
            result = bryton_sync(sync_config, progress=progress)
        except BrytonSyncError as exc:
            if use_json:
                _emit_json(_bryton_result_payload(BrytonSyncResult(), ok=False, error=str(exc)))
            else:
                print(f"✗ {exc}", file=sys.stderr)
            return EXIT_SYNC_ERROR
        except Exception as exc:  # noqa: BLE001
            if use_json:
                _emit_json(_bryton_result_payload(BrytonSyncResult(), ok=False, error=str(exc)))
            else:
                print(f"✗ Unexpected error: {exc}", file=sys.stderr)
            return EXIT_SYNC_ERROR

        ok = result.failed == 0
        if use_json:
            _emit_json(_bryton_result_payload(result, ok=ok))
        else:
            _emit_bryton_text_summary(result)
        return EXIT_OK if ok else EXIT_SYNC_ERROR

    sync_config = _build_igpsport_sync_config(
        credentials,
        config,
        max_activities=args.max_activities,
        force_resync=True if args.force_resync else None,
        activity_type=args.activity_type,
        download_dir=args.download_dir,
        delete_after_upload=delete_after_upload,
    )
    try:
        result = igpsport_sync(sync_config, progress=progress)
    except IgpSyncError as exc:
        if use_json:
            _emit_json(_igpsport_result_payload(IgpSyncResult(), ok=False, error=str(exc)))
        else:
            print(f"✗ {exc}", file=sys.stderr)
        return EXIT_SYNC_ERROR
    except Exception as exc:  # noqa: BLE001
        if use_json:
            _emit_json(_igpsport_result_payload(IgpSyncResult(), ok=False, error=str(exc)))
        else:
            print(f"✗ Unexpected error: {exc}", file=sys.stderr)
        return EXIT_SYNC_ERROR

    ok = result.failed == 0
    if use_json:
        _emit_json(_igpsport_result_payload(result, ok=ok))
    else:
        _emit_igpsport_text_summary(result)

    return EXIT_OK if ok else EXIT_SYNC_ERROR


def cmd_upload_workouts(args: argparse.Namespace) -> int:
    config = cli_config_module.load()
    use_json = args.json
    source = args.source

    try:
        env_path = resolve_env_path(
            env_file=Path(args.env_file) if args.env_file else None,
            config_env_file=config.env_file or None,
        )
        credentials = load_credentials(env_path, source=source)
    except CliConfigError as exc:
        if use_json:
            _emit_json({"ok": False, "source": source, "error": str(exc)})
        else:
            print(exc, file=sys.stderr)
        return EXIT_CONFIG_ERROR

    def progress(message: str) -> None:
        print(message, file=sys.stderr)

    if source == "bryton":
        upload_config = _build_bryton_workout_upload_config(
            credentials,
            config,
            workout_days_ahead=args.workout_days_ahead,
            force_resync=True if args.force_resync else None,
        )
        try:
            result = bryton_upload_workouts(upload_config, progress=progress)
        except BrytonSyncError as exc:
            if use_json:
                _emit_json(
                    _workout_result_payload(
                        BrytonWorkoutUploadResult(), ok=False, source=source, error=str(exc)
                    )
                )
            else:
                print(f"✗ {exc}", file=sys.stderr)
            return EXIT_SYNC_ERROR
        except Exception as exc:  # noqa: BLE001
            if use_json:
                _emit_json(
                    _workout_result_payload(
                        BrytonWorkoutUploadResult(), ok=False, source=source, error=str(exc)
                    )
                )
            else:
                print(f"✗ Unexpected error: {exc}", file=sys.stderr)
            return EXIT_SYNC_ERROR

        if result.uploaded_map or result.pruned_keys:
            apply_uploaded_bryton_workout_map(config.uploaded_bryton_workouts, result)
            cli_config_module.save(config)

        ok = result.failed == 0
        if use_json:
            _emit_json(_workout_result_payload(result, ok=ok, source=source))
        else:
            _emit_workout_text_summary(result)
        return EXIT_OK if ok else EXIT_SYNC_ERROR

    upload_config = _build_workout_upload_config(
        credentials,
        config,
        workout_days_ahead=args.workout_days_ahead,
        force_resync=True if args.force_resync else None,
    )

    try:
        result = upload_workouts(upload_config, progress=progress)
    except IgpSyncError as exc:
        if use_json:
            _emit_json(
                _workout_result_payload(
                    WorkoutUploadResult(), ok=False, source=source, error=str(exc)
                )
            )
        else:
            print(f"✗ {exc}", file=sys.stderr)
        return EXIT_SYNC_ERROR
    except Exception as exc:  # noqa: BLE001
        if use_json:
            _emit_json(
                _workout_result_payload(
                    WorkoutUploadResult(), ok=False, source=source, error=str(exc)
                )
            )
        else:
            print(f"✗ Unexpected error: {exc}", file=sys.stderr)
        return EXIT_SYNC_ERROR

    if result.uploaded_map or result.pruned_keys:
        apply_uploaded_workout_map(config.uploaded_workouts, result)
        cli_config_module.save(config)

    ok = result.failed == 0
    if use_json:
        _emit_json(_workout_result_payload(result, ok=ok, source=source))
    else:
        _emit_workout_text_summary(result)

    return EXIT_OK if ok else EXIT_SYNC_ERROR


def cmd_sync_zones(args: argparse.Namespace) -> int:
    config = cli_config_module.load()
    use_json = args.json

    try:
        env_path = resolve_env_path(
            env_file=Path(args.env_file) if args.env_file else None,
            config_env_file=config.env_file or None,
        )
        credentials = load_credentials(env_path, source="igpsport")
    except CliConfigError as exc:
        if use_json:
            _emit_json({"ok": False, "source": "igpsport", "error": str(exc)})
        else:
            print(exc, file=sys.stderr)
        return EXIT_CONFIG_ERROR

    sync_config = ProfileSyncConfig(
        igp_user=credentials.igp_user,
        igp_password=credentials.igp_password,
        intervals_api_key=credentials.intervals_api_key,
        sport=args.sport,
    )

    def progress(message: str) -> None:
        print(message, file=sys.stderr)

    try:
        result = sync_profile_zones(sync_config, progress=progress)
    except IgpSyncError as exc:
        if use_json:
            _emit_json(profile_sync_result_payload(ProfileSyncResult(None, None), ok=False, error=str(exc)))
        else:
            print(f"✗ {exc}", file=sys.stderr)
        return EXIT_SYNC_ERROR
    except Exception as exc:  # noqa: BLE001
        if use_json:
            _emit_json(profile_sync_result_payload(ProfileSyncResult(None, None), ok=False, error=str(exc)))
        else:
            print(f"✗ Unexpected error: {exc}", file=sys.stderr)
        return EXIT_SYNC_ERROR

    if use_json:
        _emit_json(profile_sync_result_payload(result, ok=True))
    else:
        summary = profile_sync_result_payload(result, ok=True)
        print(
            f"Done — FTP {summary.get('ftp')}, LTHR {summary.get('lthr')}, "
            f"MHR {summary.get('mhr')} synced to iGPSPORT."
        )
    return EXIT_OK


def _add_source_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        choices=("igpsport", "bryton"),
        default="igpsport",
        help="Activity source (default: igpsport).",
    )


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
        prog="intervalssync",
        description="Sync cycling activities to intervals.icu from iGPSPORT or Bryton Active.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    check_parser = subparsers.add_parser(
        "check",
        parents=[common],
        help="Validate credentials in the .env file (no network).",
    )
    _add_source_arg(check_parser)
    check_parser.set_defaults(func=cmd_check)

    sync_parser = subparsers.add_parser(
        "sync",
        parents=[common],
        help="Download recent rides and upload to intervals.icu.",
    )
    _add_source_arg(sync_parser)
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

    upload_workouts_parser = subparsers.add_parser(
        "upload-workouts",
        parents=[common],
        help="Upload planned workouts from intervals.icu to iGPSPORT or Bryton.",
    )
    _add_source_arg(upload_workouts_parser)
    upload_workouts_parser.add_argument(
        "--workout-days-ahead",
        type=int,
        metavar="N",
        help="Number of calendar days to upload (default: from cli config).",
    )
    upload_workouts_parser.add_argument(
        "--force-resync",
        action="store_true",
        help="Re-upload workouts even if already on the target device platform.",
    )
    upload_workouts_parser.set_defaults(func=cmd_upload_workouts)

    sync_zones_parser = subparsers.add_parser(
        "sync-zones",
        parents=[common],
        help="Push FTP, LTHR, max HR, and zones from intervals.icu to iGPSPORT.",
    )
    sync_zones_parser.add_argument(
        "--sport",
        default="Ride",
        metavar="TYPE",
        help='intervals.icu sport-settings key (default: "Ride").',
    )
    sync_zones_parser.set_defaults(func=cmd_sync_zones)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
