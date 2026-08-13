from typer.testing import CliRunner

from terrasatch.cli.main import app


def test_radio_command_groups_are_registered() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("agent", "channel", "callsign", "event", "simulate"):
        assert command in result.stdout


def test_simulate_radio_help_requires_no_database_connection() -> None:
    result = CliRunner().invoke(app, ["simulate", "radio", "--help"])

    assert result.exit_code == 0
    assert "--organization" in result.stdout
    assert "--site" in result.stdout
