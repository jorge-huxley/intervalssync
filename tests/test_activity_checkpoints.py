"""Successful identities survive network failures in either front-end."""

import importlib
from unittest.mock import Mock

import pytest

from intervalssync.cli import config as cli_config
from intervalssync.cli.env import IgpsportCredentials
from intervalssync.gui import config as gui_config, sync_view
from intervalssync.igpsport import core
from intervalssync.intervals_icu import ActivityIdentities, ActivityUploadResult
from test_gui_sync import _click_sync

cli = importlib.import_module("intervalssync.cli.main")


@pytest.mark.parametrize("frontend", ["cli", "gui"])
@pytest.mark.parametrize("failure", ["download", "upload", "sport_type"])
def test_checkpoint_survives_network_error_and_restart(
    tmp_path, monkeypatch, capsys, frontend, failure
):
    module = cli_config if frontend == "cli" else gui_config
    monkeypatch.setattr(module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(module, "CONFIG_PATH", tmp_path / "config.json")
    options = dict(download_dir=str(tmp_path), activity_type="GravelRide")
    config = (
        cli_config.CliConfig(**options) if frontend == "cli"
        else gui_config.AppConfig(igp_user="offline-test", stats_seeded=True, **options)
    )
    module.save(config)
    monkeypatch.setattr(cli, "resolve_env_path", lambda **kw: tmp_path / "unused.env")
    monkeypatch.setattr(cli, "load_credentials", lambda *a, **kw:
        IgpsportCredentials("offline-test", "fake", "fake")
    )
    monkeypatch.setattr(sync_view, "get_dropbox_app_key", lambda: None)
    monkeypatch.setattr(core, "login", lambda *a: {})
    monkeypatch.setattr(core, "list_activities", lambda *a: [
        core.Activity(i, "Ride", "2026-09-01") for i in (1, 2)
    ])
    monkeypatch.setattr(core, "fetch_activity_identities", lambda *a:
        ActivityIdentities({"existing-1", "existing-2"}, {})
    )
    monkeypatch.setattr(core, "resolve_fit_url", lambda s, h, ride, *a: str(ride))
    failing = True

    def download(url, path):
        if failing and failure == "download" and url == "2":
            raise core.requests.Timeout("offline timeout")
        path.write_bytes(b"FIT")

    def upload(path, title, ride, key):
        if failing and failure == "upload" and ride == 2:
            raise core.requests.Timeout("offline timeout")
        return ActivityUploadResult(f"existing-{ride}", created=failure == "sport_type")

    def set_type(*args):
        if failing:
            raise core.requests.Timeout("offline timeout")
        return True

    downloads = Mock(side_effect=download)
    uploads = Mock(side_effect=upload)
    monkeypatch.setattr(core, "download_fit", downloads)
    monkeypatch.setattr(core, "upload_to_intervals", uploads)
    monkeypatch.setattr(core, "set_activity_type", set_type)

    def run():
        if frontend == "gui":
            return _click_sync(module.load())
        args = cli._build_parser().parse_args(["sync", "--json"])
        code = cli.cmd_sync(args)
        output = capsys.readouterr().out
        assert code == (cli.EXIT_SYNC_ERROR if failing else cli.EXIT_OK)
        return output

    assert "offline timeout" in run()
    assert module.load().uploaded_activities == {"1": "existing-1"}
    failing = False
    downloads.reset_mock()
    uploads.reset_mock()
    assert "offline timeout" not in run()
    assert [call.args[0] for call in downloads.call_args_list] == ["2"]
    assert [call.args[2] for call in uploads.call_args_list] == [2]
    assert module.load().uploaded_activities == {
        "1": "existing-1", "2": "existing-2"
    }
