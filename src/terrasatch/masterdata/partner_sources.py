"""Tenant/site-scoped partner integration source resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.masterdata.models import DataSource, SourceConnection


@dataclass(frozen=True, slots=True)
class PartnerSourceContext:
    source_id: UUID
    organization_id: UUID
    site_id: UUID | None
    provider: str
    endpoint_url: str | None
    credential_reference: str | None
    configuration: dict[str, object]


async def resolve_partner_source(
    session: AsyncSession,
    *,
    organization_id: UUID,
    provider: str,
    site_id: UUID | None = None,
) -> PartnerSourceContext:
    """Resolve one enabled provider without ever selecting another tenant's source."""

    normalized_provider = provider.strip().casefold()
    sources = list(
        await session.scalars(
            select(DataSource)
            .where(
                DataSource.organization_id == organization_id,
                DataSource.enabled.is_(True),
            )
            .order_by(DataSource.created_at)
        )
    )
    candidates = [item for item in sources if item.provider.casefold() == normalized_provider]

    if site_id is not None:
        exact = [item for item in candidates if item.site_id == site_id]
        candidates = exact or [item for item in candidates if item.site_id is None]

    if not candidates:
        raise ResourceNotFound("Partner integration source is not configured for this organization")
    if len(candidates) > 1:
        raise InvalidConfiguration(
            "Multiple partner integration sources match; provide a site-specific source",
            details={
                "provider": normalized_provider,
                "site_id": str(site_id) if site_id else None,
            },
        )

    source = candidates[0]
    connection = await session.scalar(
        select(SourceConnection).where(
            SourceConnection.organization_id == organization_id,
            SourceConnection.data_source_id == source.id,
        )
    )
    if connection is None:
        raise InvalidConfiguration("Partner integration source is missing its connection record")

    return PartnerSourceContext(
        source_id=source.id,
        organization_id=organization_id,
        site_id=source.site_id,
        provider=source.provider,
        endpoint_url=connection.endpoint_url,
        credential_reference=connection.credential_reference,
        configuration=dict(source.configuration or {}),
    )


def resolve_environment_secret(reference: str | None) -> str | None:
    """Resolve only explicit env:// references; never accept raw provider secrets."""

    if reference is None:
        return None
    if not reference.startswith("env://"):
        raise InvalidConfiguration(
            "This integration currently supports only env:// credential references"
        )
    variable = reference.removeprefix("env://").strip()
    if not variable:
        raise InvalidConfiguration("Credential environment reference is empty")
    value = os.getenv(variable)
    if not value:
        raise InvalidConfiguration("Configured credential reference is unavailable")
    return value
