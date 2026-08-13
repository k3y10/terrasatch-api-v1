import pytest

from terrasatch.edge.client import EdgeApiClient


def test_edge_client_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("TERRASATCH_EDGE_API_KEY", raising=False)
    monkeypatch.setenv("TERRASATCH_API_BASE_URL", "https://api.example.test")

    with pytest.raises(RuntimeError, match="TERRASATCH_EDGE_API_KEY"):
        EdgeApiClient.from_environment()


def test_edge_client_loads_key_without_exposing_it_in_url(monkeypatch) -> None:
    monkeypatch.setenv("TERRASATCH_EDGE_API_KEY", "ts_test_secret")
    monkeypatch.setenv("TERRASATCH_API_BASE_URL", "https://api.example.test/")

    client = EdgeApiClient.from_environment()

    assert client.base_url == "https://api.example.test"
    assert client.headers == {"Authorization": "Bearer ts_test_secret"}
    assert "ts_test_secret" not in client.base_url
