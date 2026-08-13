"""Bounded dependency readiness probes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from terrasatch.api.schemas import ComponentStatus, DependencyStatus, HealthResponse
from terrasatch.config import Settings


async def _check_database(settings: Settings) -> DependencyStatus:
    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    try:
        async with asyncio.timeout(2):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except Exception as error:
        return DependencyStatus(name="database", status="unhealthy", detail=type(error).__name__)
    finally:
        await engine.dispose()
    return DependencyStatus(name="database", status="healthy")


async def _check_redis(settings: Settings) -> DependencyStatus:
    client = Redis.from_url(str(settings.redis_url), socket_connect_timeout=2, socket_timeout=2)
    try:
        async with asyncio.timeout(2):
            await client.ping()
    except Exception as error:
        return DependencyStatus(name="redis", status="unhealthy", detail=type(error).__name__)
    finally:
        await client.aclose()
    return DependencyStatus(name="redis", status="healthy")


async def check_readiness(settings: Settings) -> HealthResponse:
    """Check required backing services concurrently without leaking connection details."""

    dependencies = list(await asyncio.gather(_check_database(settings), _check_redis(settings)))
    is_healthy = all(dependency.status == "healthy" for dependency in dependencies)
    return HealthResponse(
        status="healthy" if is_healthy else "unhealthy",
        environment=settings.environment.value,
        deployment=settings.deployment_name,
        version="0.1.0",
        timestamp=datetime.now(UTC),
        dependencies=dependencies,
    )


def liveness(settings: Settings) -> HealthResponse:
    """Return process liveness without querying external services."""

    return HealthResponse(
        status="healthy",
        environment=settings.environment.value,
        deployment=settings.deployment_name,
        version="0.1.0",
        timestamp=datetime.now(UTC),
    )


async def check_worker(settings: Settings) -> ComponentStatus:
    """Check the recent worker heartbeat without considering worker state as API readiness."""

    client = Redis.from_url(str(settings.redis_url), socket_connect_timeout=2, socket_timeout=2)
    try:
        async with asyncio.timeout(2):
            heartbeat = await client.get("terrasatch:worker:heartbeat")
    except Exception as error:
        return ComponentStatus(name="worker", status="unhealthy", detail=type(error).__name__)
    finally:
        await client.aclose()
    if heartbeat is None:
        return ComponentStatus(name="worker", status="unhealthy", detail="heartbeat_missing")
    return ComponentStatus(name="worker", status="healthy")