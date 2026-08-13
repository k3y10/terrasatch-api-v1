from typer.testing import CliRunner

from terrasatch.cli.entrypoint import app


def test_installed_cli_registers_edge_command_group() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "edge" in result.stdout


def test_edge_help_exposes_receive_workflow_without_hardware() -> None:
    result = CliRunner().invoke(app, ["edge", "--help"])

    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "devices" in result.stdout
    assert "capture-rtl" in result.stdout
    assert "inspect-wav" in result.stdout
    assert "submit-text" in result.stdout
    assert "acceptance" in result.stdout


def test_capture_help_is_available_without_opening_radio() -> None:
    result = CliRunner().invoke(app, ["edge", "capture-rtl", "--help"])

    assert result.exit_code == 0
    assert "--frequency-hz" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--squelch" in result.stdout


def test_acceptance_help_marks_manual_stt_boundary() -> None:
    result = CliRunner().invoke(app, ["edge", "acceptance", "--help"])

    assert result.exit_code == 0
    assert "--frequency-hz" in result.stdout
    assert "--site" in result.stdout
    assert "--text" in result.stdout
