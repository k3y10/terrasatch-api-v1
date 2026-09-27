"""Local-only command line entry point for Satchy vNext sandbox testing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from .providers import ModelRouter, OllamaModelProvider, ProviderRegistry, StaticModelProvider
from .quality import inspect_context_quality
from .runtime import SatchyRuntime, SatchyRuntimeConfig
from .schemas import AgentRequest, ContextPacket, ExecutionMode, TaskType
from .tools import ToolRegistry, default_tool_specs

app = typer.Typer(
    name="satchy-vnext",
    help="Run the isolated Satchy vNext sandbox. No production routes or writes are used.",
)


def _load_context(path: Path) -> ContextPacket:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ContextPacket.model_validate(payload)


def _tools() -> ToolRegistry:
    registry = ToolRegistry()
    for spec in default_tool_specs():
        registry.register(spec)
    return registry


def _runtime(
    *,
    provider: str,
    model: str,
    ollama_url: str,
) -> SatchyRuntime:
    providers = ProviderRegistry()
    if provider == "ollama":
        providers.register(
            OllamaModelProvider(
                model=model,
                base_url=ollama_url,
            )
        )
    elif provider == "static":
        providers.register(StaticModelProvider())
    else:
        raise typer.BadParameter("provider must be 'ollama' or 'static'")

    return SatchyRuntime(
        config=SatchyRuntimeConfig(
            enabled=True,
            mode=ExecutionMode.SANDBOX,
        ),
        router=ModelRouter(providers),
        tools=_tools(),
    )


@app.command("run")
def run_sandbox(
    context_file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    message: Annotated[str, typer.Option("--message", "-m")],
    provider: Annotated[str, typer.Option("--provider")] = "ollama",
    model: Annotated[str, typer.Option("--model")] = "qwen3:1.7b",
    ollama_url: Annotated[str, typer.Option("--ollama-url")] = "http://127.0.0.1:11434",
    task: Annotated[TaskType, typer.Option("--task")] = TaskType.QUESTION,
) -> None:
    """Run one isolated Satchy request against a saved ContextPacket."""

    context = _load_context(context_file)
    runtime = _runtime(provider=provider, model=model, ollama_url=ollama_url)
    request = AgentRequest(
        message=message,
        context=context,
        task_type=task,
    )
    result = asyncio.run(runtime.run(request))
    typer.echo(result.model_dump_json(indent=2))


@app.command("inspect-context")
def inspect_context(
    context_file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
) -> None:
    """Inspect evidence freshness, contradictions, and context quality locally."""

    context = _load_context(context_file)
    report = inspect_context_quality(context)
    typer.echo(report.model_dump_json(indent=2))
