import re

from typer.testing import CliRunner

from terrasatch.cli.entrypoint import app


def _plain(output: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", output)


def test_installed_cli_registers_radio_command_groups() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "agent" in result.stdout
    assert "channel" in result.stdout
    assert "callsign" in result.stdout
    assert "event" in result.stdout
    assert "simulate" in result.stdout


def test_simulate_radio_help_is_available_without_database_access() -> None:
    result = CliRunner().invoke(app, ["simulate", "radio", "--help"])

    assert result.exit_code == 0
    output = _plain(result.stdout)
    assert "--organization" in output
    assert "--site" in output
    assert "--json" in output


def test_event_show_help_is_available() -> None:
    result = CliRunner().invoke(app, ["event", "show", "--help"])

    assert result.exit_code == 0
    assert "--organization" in _plain(result.stdout)
