"""Model-provider abstraction and routing for the isolated Satchy vNext runtime."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from .schemas import (
    Connectivity,
    ModelRoute,
    ModelUsage,
    RiskLevel,
    TaskType,
)


class ModelProviderError(RuntimeError):
    pass


class ModelRequest(BaseModel):
    system: str
    user: str
    response_schema: dict[str, Any]
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_tokens: int = Field(default=2000, ge=64, le=32000)


class ModelOutput(BaseModel):
    data: dict[str, Any]
    usage: ModelUsage


class ModelProvider(Protocol):
    name: str
    model: str
    local: bool
    capabilities: frozenset[str]

    async def generate(self, request: ModelRequest) -> ModelOutput: ...


@dataclass(frozen=True, slots=True)
class ProviderEntry:
    provider: ModelProvider
    priority: int = 100
    enabled: bool = True
    cost_tier: int = 0


class ProviderRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, ProviderEntry] = {}

    def register(
        self,
        provider: ModelProvider,
        *,
        priority: int = 100,
        enabled: bool = True,
        cost_tier: int = 0,
    ) -> None:
        self._entries[provider.name] = ProviderEntry(
            provider=provider,
            priority=priority,
            enabled=enabled,
            cost_tier=cost_tier,
        )

    def entries(self) -> list[ProviderEntry]:
        return sorted(
            (entry for entry in self._entries.values() if entry.enabled),
            key=lambda item: (item.priority, item.cost_tier),
        )


class StaticModelProvider:
    """Deterministic test/sandbox provider. Never calls a network service."""

    name = "static"
    model = "static-v1"
    local = True
    capabilities = frozenset({"fast", "reasoning", "structured"})

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {
            "answer": "No model-backed answer is configured for this isolated Satchy runtime.",
            "confidence": 0.5,
            "evidence_ids": [],
            "missing_context": [],
            "tool_requests": [],
            "proposed_actions": [],
            "follow_up_required": False,
        }

    async def generate(self, request: ModelRequest) -> ModelOutput:
        _ = request
        return ModelOutput(
            data=dict(self.response),
            usage=ModelUsage(
                provider=self.name,
                model=self.model,
                input_tokens=None,
                output_tokens=None,
                latency_ms=0,
                estimated_cost_usd=0.0,
            ),
        )


class OllamaModelProvider:
    """Local structured-output provider for disconnected or zero-API-cost operation."""

    name = "ollama"
    local = True
    capabilities = frozenset({"fast", "reasoning", "structured", "offline"})

    def __init__(
        self,
        *,
        model: str = "qwen3:1.7b",
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def generate(self, request: ModelRequest) -> ModelOutput:
        started = time.perf_counter()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
            "format": request.response_schema,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                raw = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelProviderError(f"Ollama request failed: {exc}") from exc

        message = raw.get("message") if isinstance(raw, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ModelProviderError("Ollama returned no structured content")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelProviderError("Ollama returned invalid JSON") from exc

        prompt_eval_count = raw.get("prompt_eval_count") if isinstance(raw, dict) else None
        eval_count = raw.get("eval_count") if isinstance(raw, dict) else None
        return ModelOutput(
            data=data,
            usage=ModelUsage(
                provider=self.name,
                model=self.model,
                input_tokens=prompt_eval_count if isinstance(prompt_eval_count, int) else None,
                output_tokens=eval_count if isinstance(eval_count, int) else None,
                latency_ms=int((time.perf_counter() - started) * 1000),
                estimated_cost_usd=0.0,
            ),
        )


class ModelRouter:
    """Cost- and connectivity-aware router with a local-first field bias."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    def select(
        self,
        *,
        task_type: TaskType,
        connectivity: Connectivity,
        risk_level: RiskLevel,
        prefer_local: bool,
    ) -> tuple[ModelProvider, ModelRoute]:
        entries = self.registry.entries()
        if connectivity == Connectivity.OFFLINE:
            entries = [entry for entry in entries if entry.provider.local]
        if prefer_local:
            entries.sort(key=lambda item: (not item.provider.local, item.priority, item.cost_tier))

        capability = "reasoning" if task_type in {TaskType.ANALYZE, TaskType.PLAN, TaskType.COMMAND} else "fast"
        capable = [entry for entry in entries if capability in entry.provider.capabilities]
        if capable:
            entries = capable
        if risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            reasoning = [entry for entry in entries if "reasoning" in entry.provider.capabilities]
            if reasoning:
                entries = reasoning
        if not entries:
            raise ModelProviderError("No eligible Satchy model provider is available")

        chosen = entries[0].provider
        reason = (
            f"Selected {chosen.name}/{chosen.model}; task={task_type.value}, "
            f"connectivity={connectivity.value}, risk={risk_level.value}, "
            f"prefer_local={prefer_local}."
        )
        return chosen, ModelRoute(
            provider=chosen.name,
            model=chosen.model,
            reason=reason,
            local=chosen.local,
            capabilities=sorted(chosen.capabilities),
        )
