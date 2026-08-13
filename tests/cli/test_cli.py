import json

from typer.testing import CliRunner

from terrasatch.cli.main import _redact_url, app


def test_cli_help_is_available_without_configuration() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Operate the TerraSatch API platform" in result.stdout


def test_config_show_masks_database_password() -> None:
    result = CliRunner().invoke(app, ["config", "show", "--json"])

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert "***" in output["database_url"]
    assert "terrasatch" in output["database_url"]


def test_redact_url_preserves_host_and_hides_password() -> None:
    redacted = _redact_url("postgresql+asyncpg://operator:radio-secret@db.example:5432/core")

    assert redacted == "postgresql+asyncpg://operator:***@db.example:5432/core"


def test_deployment_check_rejects_non_http_url_without_network_access() -> None:
    result = CliRunner().invoke(app, ["deployment", "check", "--base-url", "ftp://api.example"])

    assert result.exit_code == 1
    assert "absolute http or https URL" in result.output + result.stderr