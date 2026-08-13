from terrasatch.config import Environment, Settings


def test_documented_environment_and_cors_variables_are_parsed(monkeypatch) -> None:
    monkeypatch.setenv("TERRASATCH_ENV", "staging")
    monkeypatch.setenv(
        "TERRASATCH_CORS_ORIGINS",
        "https://console.example, https://partner.example/",
    )

    settings = Settings()

    assert settings.environment is Environment.STAGING
    assert settings.cors_origins == ["https://console.example", "https://partner.example"]


def test_local_defaults_are_safe_for_cli_discovery() -> None:
    settings = Settings()

    assert settings.environment is Environment.LOCAL
    assert settings.database_url.scheme == "postgresql+asyncpg"
    assert settings.redis_url.scheme == "redis"