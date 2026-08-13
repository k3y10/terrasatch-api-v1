"""FastAPI dependencies for server-to-server API-key authorization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from terrasatch.auth.api_keys import hash_api_key
from terrasatch.auth.models import ApiKey
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated service identity with a server-derived tenant boundary."""

    organization_id: UUID
    api_key_id: UUID
    scopes: frozenset[str]


async def authenticate_token(settings: Settings, token: str) -> Principal:
    """Resolve one raw service token for HTTP or realtime transports."""

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )

    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        api_key = await session.scalar(
            select(ApiKey).where(
                ApiKey.secret_hash == hash_api_key(token),
                ApiKey.revoked_at.is_(None),
            )
        )
        if api_key is None or (api_key.expires_at and api_key.expires_at <= datetime.now(UTC)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
            )
        api_key.last_used_at = datetime.now(UTC)
        await session.commit()
        return Principal(
            organization_id=api_key.organization_id,
            api_key_id=api_key.id,
            scopes=frozenset(api_key.scopes),
        )


async def get_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ] = None,
) -> Principal:
    """Resolve a non-revoked bearer key without ever trusting a tenant header."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
        )
    return await authenticate_token(request.app.state.settings, credentials.credentials)


def require_scope(scope: str):
    """Require one named scope or the tenant-local admin scope."""

    async def check_scope(principal: Annotated[Principal, Security(get_principal)]) -> Principal:
        if scope not in principal.scopes and "admin" not in principal.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key scope is insufficient",
            )
        return principal

    return check_scope
