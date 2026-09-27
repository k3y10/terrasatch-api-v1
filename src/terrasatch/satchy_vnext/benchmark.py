"""Reusable benchmark runner for Satchy vNext promotion testing."""

from __future__ import annotations

from statistics import mean

from pydantic import BaseModel, Field

from .evals import EvalCase, EvalScore, evaluate_run, promotion_report
from .runtime import SatchyRuntime
from .schemas import AgentRequest, AgentRun


class BenchmarkCase(BaseModel):
    name: str
    request: AgentRequest
    evaluation: EvalCase


class BenchmarkCaseResult(BaseModel):
    name: str
    run: AgentRun
    score: EvalScore


class BenchmarkReport(BaseModel):
    case_count: int = Field(ge=0)
    passed: bool
    mean_composite: float = Field(ge=0, le=1)
    results: list[BenchmarkCaseResult] = Field(default_factory=list)
    promotion_reasons: list[str] = Field(default_factory=list)


async def run_benchmark(
    runtime: SatchyRuntime,
    cases: list[BenchmarkCase],
) -> BenchmarkReport:
    results: list[BenchmarkCaseResult] = []
    for case in cases:
        run = await runtime.run(case.request)
        score = evaluate_run(run, case.evaluation)
        results.append(
            BenchmarkCaseResult(
                name=case.name,
                run=run,
                score=score,
            )
        )

    scores = [item.score for item in results]
    promotion = promotion_report(scores)
    return BenchmarkReport(
        case_count=len(results),
        passed=promotion.passed,
        mean_composite=(
            round(mean(item.composite for item in scores), 4)
            if scores
            else 0.0
        ),
        results=results,
        promotion_reasons=promotion.reasons,
    )
