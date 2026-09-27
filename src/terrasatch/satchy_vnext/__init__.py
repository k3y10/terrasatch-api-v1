"""Satchy vNext isolated agent runtime.

This package is intentionally not imported by TerraSatch production routes.
"""

from .benchmark import BenchmarkCase, BenchmarkReport, run_benchmark
from .bridge import context_packet_from_current
from .corpus import seed_benchmark_cases
from .domains import DOMAIN_DEFINITIONS, definition_for, infer_domain
from .evals import (
    EvalCase,
    EvalScore,
    PromotionReport,
    PromotionThresholds,
    evaluate_run,
    promotion_report,
)
from .impact import ImpactMeasurement, ImpactSummary, summarize_impact
from .observability import JsonlTraceStore
from .policy import PolicyEngine
from .providers import (
    ModelProviderError,
    ModelRouter,
    OllamaModelProvider,
    ProviderRegistry,
    StaticModelProvider,
)
from .quality import (
    ContextQualityReport,
    QualityIssue,
    QualityIssueType,
    inspect_context_quality,
)
from .runtime import SatchyRuntime, SatchyRuntimeConfig
from .schemas import (
    AgentPlan,
    AgentRequest,
    AgentRun,
    ClaimType,
    Connectivity,
    ContextPacket,
    DomainProfile,
    EvidenceClass,
    EvidenceRef,
    ExecutionMode,
    GroundedClaim,
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
    "BenchmarkCase",
    "BenchmarkReport",
    "ClaimType",
    "Connectivity",
    "ContextQualityReport",
    "ContextPacket",
    "DOMAIN_DEFINITIONS",
    "DomainProfile",
    "EvalCase",
    "EvalScore",
    "EvidenceClass",
    "EvidenceRef",
    "ExecutionMode",
    "GroundedClaim",
    "ImpactMeasurement",
    "ImpactSummary",
    "JsonlTraceStore",
    "ModelProviderError",
    "ModelRouter",
    "OllamaModelProvider",
    "PolicyEngine",
    "PromotionReport",
    "PromotionThresholds",
    "ProposedAction",
    "ProviderRegistry",
    "QualityIssue",
    "QualityIssueType",
    "RiskLevel",
    "RunStatus",
    "SatchyRuntime",
    "SatchyRuntimeConfig",
    "StaticModelProvider",
    "TaskType",
    "ToolEffect",
    "ToolRegistry",
    "ToolSpec",
    "context_packet_from_current",
    "default_tool_specs",
    "definition_for",
    "evaluate_run",
    "infer_domain",
    "inspect_context_quality",
    "promotion_report",
    "run_benchmark",
    "seed_benchmark_cases",
    "summarize_impact",
]
