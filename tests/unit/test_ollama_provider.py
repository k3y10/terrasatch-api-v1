from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from terrasatch.intelligence.core import EventType
from terrasatch.intelligence.providers import (
    FallbackIntelligenceProvider,
    IntelligenceProviderError,
    OllamaIntelligenceProvider,
    build_intelligence_provider,
)


def _transport_with_content(content: str, *, status: int = 200) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["stream"] is False
        assert isinstance(payload["format"], dict)
        assert payload["options"]["temperature"] == 0
        return httpx.Response(status, json={"message": {"content": content}})

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_ollama_provider_returns_validated_event_and_strips_coordinates() -> None:
    content = json.dumps(
        {
            "events": [
                {
                    "event_type": "OBSERVATION",
                    "summary": "Shooting cracks reported below Cardiff Bowl.",
                    "callsign": "Patrol 4",
                    "location_text": "Cardiff Bowl",
                    "latitude": 40.123,
                    "longitude": -111.456,
                    "elevation_ft": 9800,
                    "aspect": "NE",
                    "severity": "moderate",
                    "confidence": 0.91,
                    "data": {"observation": "shooting_cracks"},
                }
            ]
        }
    )
    provider = OllamaIntelligenceProvider(
        model="qwen3:1.7b",
        transport=_transport_with_content(content),
    )
    events = await provider.extract_events(
        text="Patrol 4 reports shooting cracks below Cardiff Bowl northeast around 9800.",
    )
    assert len(events) == 1
    event = events[0]
    assert event.event_type == EventType.OBSERVATION
    assert event.location_text == "Cardiff Bowl"
    assert event.latitude is None
    assert event.longitude is None
    assert event.data["intelligence_provider"] == "ollama"
    assert event.data["intelligence_model"] == "qwen3:1.7b"


@pytest.mark.asyncio
async def test_ollama_provider_rejects_invalid_structured_output() -> None:
    provider = OllamaIntelligenceProvider(transport=_transport_with_content("not-json"))
    with pytest.raises(IntelligenceProviderError, match="invalid structured"):
        await provider.extract_events(text="Wind loading reported.")


@pytest.mark.asyncio
async def test_fallback_provider_keeps_pipeline_alive_when_local_model_is_down() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="offline")

    primary = OllamaIntelligenceProvider(transport=httpx.MockTransport(handler))
    provider = FallbackIntelligenceProvider(primary)
    events = await provider.extract_events(
        text="Patrol 4 reports shooting cracks on the east aspect around 9800 feet."
    )
    assert events[0].event_type == EventType.OBSERVATION
    assert events[0].data["intelligence_provider"] == "deterministic"
    assert events[0].data["intelligence_fallback"] is True


def test_provider_factory_defaults_to_deterministic() -> None:
    settings = SimpleNamespace(
        intelligence_provider="deterministic",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3:1.7b",
        intelligence_timeout_seconds=20.0,
        intelligence_fallback_to_deterministic=True,
    )
    provider = build_intelligence_provider(settings)
    assert provider.name == "deterministic"


def test_provider_factory_builds_resilient_ollama() -> None:
    settings = SimpleNamespace(
        intelligence_provider="ollama",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3:1.7b",
        intelligence_timeout_seconds=20.0,
        intelligence_fallback_to_deterministic=True,
    )
    provider = build_intelligence_provider(settings)
    assert isinstance(provider, FallbackIntelligenceProvider)
