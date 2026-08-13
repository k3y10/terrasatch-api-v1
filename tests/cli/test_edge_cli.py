from typer.testing import CliRunner

from terrasatch.cli.entrypoint import app


def test_installed_cli_registers_edge_group() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "edge" in result.stdout


def test_edge_help_is_available_without_receiver() -> None:
    result = CliRunner().invoke(app, ["edge", "--help"])

    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "rtl" in result.stdout
    assert "audio" in result.stdout
    assert "api" in result.stdout
    assert "submit-text" in result.stdout


def test_rtl_capture_help_requires_no_connected_device() -> None:
    result = CliRunner().invoke(app, ["edge", "rtl", "capture", "--help"])

    assert result.exit_code == 0
    assert "--frequency-hz" in result.stdout
    assert "--output" in result.stdout
    assert "--submit-text" in result.stdout
    assert "automatic STT" in result.stdout
