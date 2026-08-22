"""Low-cost model-backed intelligence providers for TerraEngine."""

from __future__ import annotations

import json
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from .core import DeterministicIntelligenceProvider, ExtractedEvent, IntelligenceProvider


class IntelligenceProviderError(RuntimeError):
    """Raised when a model-backed intelligence provider cannot produce a valid result."""


class _EventEnvelope(BaseModel):
    events: list[ExtractedEvent] = Field(default_factory=list, max_length=16)


_SYSTEM_PROMPT = """You are Satchy, TerraSatch's operational extraction layer.
Convert the supplied field-radio transcript into structured operational events.
Rules:
- Extract only facts supported by the transcript or explicit metadata.
- Never invent coordinates. latitude and longitude must be null; spatial grounding happens later.
- Keep named places in location_text exactly enough for a trusted terrain resolver to match them.
- Preserve uncertainty in confidence. Do not turn guesses into facts.
- Preserve negation. Phrases such as \"no avalanches observed\" are negative findings,
  not avalanche events. Never infer a positive hazard solely from a keyword inside a
  negated phrase.
- When the transcript explicitly reports no avalanche activity, prefer an OBSERVATION
  event and preserve that negative finding instead of creating an AVALANCHE event.
- Use concise factual summaries, not advice.
- Return no more than necessary events.
"""


class OllamaIntelligenceProvider:
    """Schema-constrained local Ollama provider with no per-request API charge."""

    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3:1.7b",
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def extract_events(
        self,
        *,
        text: str,
        callsign_hint: str | None = None,
    ) -> list[ExtractedEvent]:
        normalized = " ".join(text.split()).strip()
        if not normalized:
            return []

        user_payload = {"transcript": normalized, "callsign_hint": callsign_hint}
        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "stream": False,
            "format": _EventEnvelope.model_json_schema(),
            "options": {"temperature": 0},
        }

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post("/api/chat", json=request_payload)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IntelligenceProviderError(f"Ollama request failed: {exc}") from exc

        message = payload.get("message") if isinstance(payload, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise IntelligenceProviderError("Ollama returned no structured event content")

        try:
            envelope = _EventEnvelope.model_validate_json(content)
        except ValidationError as exc:
            raise IntelligenceProviderError(
                "Ollama returned invalid structured event data"
            ) from exc

        sanitized: list[ExtractedEvent] = []
        for item in envelope.events:
            data = dict(item.data)
            data["intelligence_provider"] = self.name
            data["intelligence_model"] = self.model
            sanitized.append(
                item.model_copy(
                    update={
                        "latitude": None,
                        "longitude": None,
                        "data": data,
                    }
                )
            )
        return sanitized


class FallbackIntelligenceProvider:
    """Use a model-backed provider when available and deterministic extraction otherwise."""

    name = "fallback"

    def __init__(
        self,
        primary: IntelligenceProvider,
        fallback: IntelligenceProvider | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback or DeterministicIntelligenceProvider()

    async def extract_events(
        self,
        *,
        text: str,
        callsign_hint: str | None = None,
    ) -> list[ExtractedEvent]:
        try:
            return await self.primary.extract_events(text=text, callsign_hint=callsign_hint)
        except IntelligenceProviderError:
            events = await self.fallback.extract_events(text=text, callsign_hint=callsign_hint)
            for event in events:
                data = dict(event.data)
                data["intelligence_fallback"] = True
                event.data = data
            return events


class IntelligenceSettings(Protocol):
    intelligence_provider: str
    ollama_base_url: object
    ollama_model: str
    intelligence_timeout_seconds: float
    intelligence_fallback_to_deterministic: bool


def build_intelligence_provider(settings: IntelligenceSettings) -> IntelligenceProvider:
    provider_name = settings.intelligence_provider.strip().lower()
    if provider_name == "deterministic":
        return DeterministicIntelligenceProvider()
    if provider_name == "ollama":
        provider: IntelligenceProvider = OllamaIntelligenceProvider(
            base_url=str(settings.ollama_base_url),
            model=settings.ollama_model,
            timeout_seconds=settings.intelligence_timeout_seconds,
        )
        if settings.intelligence_fallback_to_deterministic:
            provider = FallbackIntelligenceProvider(provider)
        return provider
    raise IntelligenceProviderError(f"Unsupported intelligence provider: {provider_name}")
