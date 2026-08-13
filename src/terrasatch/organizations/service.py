"""Tenant creation and selection with server-side ownership boundaries."""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.errors import InvalidConfiguration
from terrasatch.identity.models import Account, Organization, Site

DEFAULT_ACCOUNT_NAME = "TerraSatch Default Account"


def slugify(value: str) -> str:
    """Create a stable, human-readable slug and reject empty values."""

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise InvalidConfiguration("Name must include at least one letter or number")
    return slug[:100]


async def _default_account(session: AsyncSession) -> Account:
    account = await session.scalar(select(Account).where(Account.name == DEFAULT_ACCOUNT_NAME))
    if account is None:
        account = Account(name=DEFAULT_ACCOUNT_NAME)
        session.add(account)
        await session.flush()
    return account


async def create_organization(session: AsyncSession, *, name: str) -> Organization:
    """Create an enabled organization under the local bootstrap account."""

    account = await _default_account(session)
    slug = slugify(name)
    existing = await session.scalar(
        select(Organization).where(Organization.account_id == account.id, Organization.slug == slug)
    )
    if existing is not None:
        raise InvalidConfiguration(f"Organization slug '{slug}' already exists")
    organization = Organization(account_id=account.id, name=name.strip(), slug=slug)
    session.add(organization)
    await session.flush()
    return organization


def _selector_query(selector: str) -> Select[tuple[Organization]]:
    """Match a tenant selector by UUID, slug, or exact display name."""

    try:
        organization_id = UUID(selector)
    except ValueError:
        return select(Organization).where(
            Organization.enabled.is_(True),
            (Organization.slug == selector) | (Organization.name == selector),
        )
    return select(Organization).where(
        Organization.enabled.is_(True), Organization.id == organization_id
    )


async def resolve_organization(session: AsyncSession, selector: str | None = None) -> Organization:
    """Resolve only an explicit selector or the sole enabled organization.

    Commands must not silently pick an organization in a multi-tenant deployment.
    """

    if selector:
        organization = await session.scalar(_selector_query(selector))
        if organization is None:
            raise InvalidConfiguration("Organization was not found or is disabled")
        return organization

    organizations = list(
        await session.scalars(select(Organization).where(Organization.enabled.is_(True)).limit(2))
    )
    if len(organizations) == 1:
        return organizations[0]
    if not organizations:
        raise InvalidConfiguration(
            "No organization exists; run 'terrasatch org create <name>' first"
        )
    raise InvalidConfiguration("Multiple organizations exist; select one with --organization")


async def create_site(
    session: AsyncSession,
    *,
    name: str,
    organization_selector: str | None = None,
) -> Site:
    """Create a site under the explicitly resolved organization."""

    organization = await resolve_organization(session, organization_selector)
    slug = slugify(name)
    existing = await session.scalar(
        select(Site).where(Site.organization_id == organization.id, Site.slug == slug)
    )
    if existing is not None:
        raise InvalidConfiguration(f"Site slug '{slug}' already exists for this organization")
    site = Site(organization_id=organization.id, name=name.strip(), slug=slug)
    session.add(site)
    await session.flush()
    return site


async def list_organizations(session: AsyncSession) -> list[Organization]:
    """List enabled organizations for local administrative CLI operations."""

    return list(await session.scalars(select(Organization).order_by(Organization.name)))


async def list_sites(
    session: AsyncSession,
    *,
    organization_selector: str | None = None,
) -> tuple[Organization, list[Site]]:
    """Return only sites belonging to the resolved organization."""

    organization = await resolve_organization(session, organization_selector)
    sites = list(
        await session.scalars(
            select(Site).where(Site.organization_id == organization.id).order_by(Site.name)
        )
    )
    return organization, sites