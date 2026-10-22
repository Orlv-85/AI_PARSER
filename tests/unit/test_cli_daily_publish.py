import json

from typer.testing import CliRunner

import app.cli.main as cli_main


def _session():
    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    return Session()


def _no_op():
    return None


def _settings():
    return object()


def _held_report(*_args):
    return {"report_date": "2026-10-21", "state": "held_collection_paused"}


def _held_reports(*_args):
    return [_held_report()]


def test_daily_publish_exits_two_for_held_collection(monkeypatch):
    monkeypatch.setattr(cli_main, "create_all", _no_op)
    monkeypatch.setattr(cli_main, "SessionLocal", _session)
    monkeypatch.setattr(cli_main, "get_settings", _settings)
    monkeypatch.setattr(cli_main, "publish_day", _held_report)

    result = CliRunner().invoke(cli_main.app, ["daily-publish"])

    assert result.exit_code == 2
    assert json.loads(result.stdout)["state"] == "held_collection_paused"


def test_daily_publish_catch_up_exits_two_when_a_day_is_held(monkeypatch):
    monkeypatch.setattr(cli_main, "create_all", _no_op)
    monkeypatch.setattr(cli_main, "SessionLocal", _session)
    monkeypatch.setattr(cli_main, "get_settings", _settings)
    monkeypatch.setattr(cli_main, "publish_catch_up", _held_reports)

    result = CliRunner().invoke(cli_main.app, ["daily-publish", "--catch-up"])

    assert result.exit_code == 2
    assert json.loads(result.stdout)["reports"][0]["state"] == "held_collection_paused"
