"""Satchy vNext isolated agent runtime.

This package is intentionally not imported by TerraSatch production routes.
"""

from .domains import DOMAIN_DEFINITIONS, definition_for, infer_domain
from .evals import (
    EvalCase,
    EvalScore,
    PromotionReport,
    PromotionThresholds,
    evaluate_run,
    promotion_report,
)
from .policy import PolicyEngine
from .providers import (
    ModelProviderError,
    ModelRouter,
    OllamaModelProvider,
    ProviderRegistry,
    StaticModelProvider,
)
from .runtime import SatchyRuntime, SatchyRuntimeConfig
from .schemas import (
    AgentPlan,
    AgentRequest,
    AgentRun,
    Connectivity,
    ContextPacket,
    DomainProfile,
    EvidenceClass,
    EvidenceRef,
    ExecutionMode,
    ProposedAction,
    RiskLevel,
    RunStatus,
    TaskType,
    ToolEffect,
)
from .tools import ToolRegistry, ToolSpec, default_tool_specs

__all__ = [
    "AgentPlan",
    "AgentRequest",
    "AgentRun",
    "Connectivity",
    "ContextPacket",
    "DOMAIN_DEFINITIONS",
    "DomainProfile",
    "EvalCase",
    "EvalScore",
    "EvidenceClass",
    "EvidenceRef",
    "ExecutionMode",
    "ModelProviderError",
    "ModelRouter",
    "OllamaModelProvider",
    "PolicyEngine",
    "PromotionReport",
    "PromotionThresholds",
    "ProposedAction",
    "ProviderRegistry",
    "RiskLevel",
    "RunStatus",
    "SatchyRuntime",
    "SatchyRuntimeConfig",
    "StaticModelProvider",
    "TaskType",
    "ToolEffect",
    "ToolRegistry",
    "ToolSpec",
    "default_tool_specs",
    "definition_for",
    "evaluate_run",
    "infer_domain",
    "promotion_report",
]
