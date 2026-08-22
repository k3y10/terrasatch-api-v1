"""Allow-listed master-data commands for the existing browser operations console."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.commands import AdminCommandResult
from terrasatch.errors import InvalidConfiguration
from terrasatch.masterdata.models import DataSource
from terrasatch.masterdata.service import (
    enqueue_source_sync,
    inspect_data,
    list_backup_snapshots,
    list_data_sources,
    list_sync_runs,
    resolve_data_source,
    resolve_organization_id,
)


async def run_masterdata_command(
    session: AsyncSession,
    *,
    verb: str,
    args: list[str],
    selected_organization: str | None,
) -> AdminCommandResult | None:
    """Return ``None`` when the command belongs to another allow-listed router."""

    normalized = verb.lower()
    if normalized == "database" and args == ["status"]:
        await session.execute(select(1))
        return AdminCommandResult(["database: reachable", "query: SELECT 1", "status: healthy"])

    if normalized == "backup" and (not args or args == ["status"]):
        snapshots = await list_backup_snapshots(session, limit=10)
        if not snapshots:
            return AdminCommandResult(
                [
                    "backup visibility: no snapshots reported",
                    "note: backup execution remains outside the browser control plane",
                ]
            )
        lines = ["TYPE                 PROVIDER      STATUS       RESTORE TEST"]
        lines.extend(
            f"{item.backup_type[:20]:20} {item.provider[:13]:13} "
            f"{item.status[:12]:12} {item.restore_test_status}"
            for item in snapshots
        )
        return AdminCommandResult(lines)

    if normalized not in {"source", "sources", "sync", "inspect"}:
        return None
    if not selected_organization:
        raise InvalidConfiguration("Select an organization first with: org select <id|slug>")
    organization_id = await resolve_organization_id(session, selected_organization)

    if normalized in {"source", "sources"}:
        action = args[0].lower() if args else "list"
        if action == "list":
            sources = await list_data_sources(session, organization_id=organization_id)
            lines = [
                "ID                                   PROVIDER             STATUS      ADAPTER"
            ]
            lines.extend(
                f"{source.id}  {source.provider[:20]:20} "
                f"{source.status[:11]:11} {source.adapter_key}"
                for source in sources
            )
            return AdminCommandResult(lines or ["no sources"])
        if action in {"show", "status"} and len(args) >= 2:
            source = await resolve_data_source(
                session,
                organization_id=organization_id,
                selector=args[1],
            )
            return AdminCommandResult(_source_lines(source))
        if action == "sync" and len(args) >= 2:
            run = await enqueue_source_sync(
                session,
                organization_id=organization_id,
                source_selector=args[1],
                trigger="admin_command",
            )
            return AdminCommandResult(
                [f"[queued] source sync -> {run.id}", "provider work will run outside the API path"]
            )
        raise InvalidConfiguration(
            "Usage: source list | source show <id|slug> | source sync <id|slug>"
        )

    if normalized == "sync":
        if not args or args[0].lower() in {"list", "status"}:
            runs = await list_sync_runs(session, organization_id=organization_id, limit=20)
            lines = [
                "ID                                   STATUS      "
                "SOURCE                               COUNTS"
            ]
            lines.extend(
                f"{run.id}  {run.status[:11]:11} {run.data_source_id}  "
                f"f={run.fetched_count} c={run.created_count} u={run.updated_count} "
                f"x={run.rejected_count}"
                for run in runs
            )
            return AdminCommandResult(lines)
        run = await enqueue_source_sync(
            session,
            organization_id=organization_id,
            source_selector=args[0],
            trigger="admin_command",
        )
        return AdminCommandResult(
            [f"[queued] source sync -> {run.id}", "provider work will run outside the API path"]
        )

    if not args:
        raise InvalidConfiguration("Usage: inspect [source|event] <id|text>")
    query = args[-1]
    results = await inspect_data(
        session,
        organization_id=organization_id,
        query=query,
        limit=10,
    )
    if not results:
        return AdminCommandResult([f"no canonical records matched: {query}"])
    lines: list[str] = []
    for item in results:
        lines.extend(
            [
                f"{item.record_type.upper()} {item.record_id}",
                f"  {item.title}",
                f"  {item.subtitle}",
                f"  provenance: {item.provenance or 'n/a'}",
                f"  spatial: {item.spatial or 'n/a'}",
            ]
        )
    return AdminCommandResult(lines)


def _source_lines(source: DataSource) -> list[str]:
    return [
        f"ID           {source.id}",
        f"NAME         {source.name}",
        f"PROVIDER     {source.provider}",
        f"KIND         {source.source_kind}",
        f"ADAPTER      {source.adapter_key}@{source.adapter_version or 'unversioned'}",
        f"STATUS       {source.status}",
        f"ENABLED      {source.enabled}",
        f"LAST SUCCESS {source.last_successful_sync or 'never'}",
        f"LAST ERROR   {source.last_error or 'none'}",
    ]
