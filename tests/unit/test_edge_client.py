from uuid import uuid4

import httpx
import pytest

from terrasatch.edge import client as edge_client


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeClient:
    last_headers: dict[str, str] | None = None
    last_path: str | None = None
    last_payload: dict[str, object] | None = None

    def __init__(self, *, base_url: str, headers: dict[str, str], timeout: float) -> None:
        assert base_url == "https://api.terrasatch.com"
        assert timeout == 15.0
        _FakeClient.last_headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def post(self, path: str, *, json: dict[str, object]) -> _FakeResponse:
        _FakeClient.last_path = path
        _FakeClient.last_payload = json
        return _FakeResponse({"transmission": {"id": "tx-1"}, "events": []})


def test_submit_text_uses_bearer_key_and_canonical_transmission_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(edge_client.httpx, "Client", _FakeClient)
    site_id = uuid4()

    result = edge_client.submit_text_transmission(
        base_url="https://api.terrasatch.com/",
        api_key=" secret-key ",
        site_id=site_id,
        text=" Patrol 4 reports east aspect loading. ",
        callsign=" Patrol 4 ",
    )

    assert result["transmission"] == {"id": "tx-1"}
    assert _FakeClient.last_headers == {"Authorization": "Bearer secret-key"}
    assert _FakeClient.last_path == "/api/v1/transmissions"
    assert _FakeClient.last_payload is not None
    assert _FakeClient.last_payload["site_id"] == str(site_id)
    assert _FakeClient.last_payload["text"] == "Patrol 4 reports east aspect loading."
    assert _FakeClient.last_payload["callsign"] == "Patrol 4"
    assert str(_FakeClient.last_payload["source_message_id"]).startswith("edge-")


def test_submit_text_rejects_blank_inputs() -> None:
    site_id = uuid4()
    with pytest.raises(ValueError):
        edge_client.submit_text_transmission(
            base_url="https://api.terrasatch.com",
            api_key="key",
            site_id=site_id,
            text="   ",
        )


def test_httpx_is_still_the_real_module() -> None:
    assert hasattr(httpx, "Client")
