"""Convenience factory for a fully local, production-isolated Satchy sandbox."""

from __future__ import annotations

from .policy import PolicyEngine
from .providers import ModelRouter, ProviderRegistry, StaticModelProvider
from .runtime import SatchyRuntime, SatchyRuntimeConfig
from .schemas import ExecutionMode
from .tools import ToolRegistry, default_tool_specs


def build_static_shadow_runtime() -> SatchyRuntime:
    providers = ProviderRegistry()
    providers.register(StaticModelProvider(), priority=0, cost_tier=0)
    tools = ToolRegistry()
    for spec in default_tool_specs():
        tools.register(spec)
    return SatchyRuntime(
        config=SatchyRuntimeConfig(
            enabled=True,
            mode=ExecutionMode.SHADOW,
            refine_after_read_tools=False,
        ),
        router=ModelRouter(providers),
        tools=tools,
        policy=PolicyEngine(),
    )
