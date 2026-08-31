import json
import os
from pathlib import Path

from typer.testing import CliRunner

from terrasatch.cli.main import _redact_url, _serialize_dotenv_value, _upsert_environment_file, app


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


def test_dotenv_serializer_quotes_compose_interpolation_characters() -> None:
    assert _serialize_dotenv_value("abc$def$ghi") == "'abc$def$ghi'"
    assert _serialize_dotenv_value("plain-secret") == "plain-secret"


def test_environment_upsert_preserves_scrypt_hash_literal(tmp_path: Path) -> None:
    destination = tmp_path / ".env"
    destination.write_text("TERRASATCH_ENV=production\nTERRASATCH_ADMIN_PASSWORD_HASH=old\n")
    scrypt_hash = (
        "scrypt$ln=14,r=8,p=1$F1T9mE0SXzce2pvNCR9qEQ$"
        "XPueOoJ5FI1PKBxonk0yjToMtJtSu3w5234GYOupQTo"
    )

    _upsert_environment_file(
        {
            "TERRASATCH_ADMIN_PASSWORD_HASH": scrypt_hash,
            "TERRASATCH_ADMIN_SESSION_SECRET": "session-secret",
        },
        destination=destination,
    )

    text = destination.read_text()
    assert f"TERRASATCH_ADMIN_PASSWORD_HASH='{scrypt_hash}'" in text
    assert "TERRASATCH_ADMIN_SESSION_SECRET=session-secret" in text
    if os.name != "nt":
        assert destination.stat().st_mode & 0o777 == 0o600
