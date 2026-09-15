"""Bounded public Checkout throttling without storing raw client identifiers."""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis
from redis.exceptions import RedisError

from terrasatch.config import Settings
from terrasatch.errors import ProviderUnavailable, RateLimitExceeded

_WINDOW_SECONDS = 3600
_IP_LIMIT = 20
_EMAIL_LIMIT = 5


def _digest(value: str) -> str:
    return hashlib.sha256(value.strip().casefold().encode("utf-8")).hexdigest()[:32]


async def enforce_checkout_rate_limit(
    settings: Settings,
    *,
    client_host: str | None,
    email: str,
) -> None:
    """Apply a one-hour sliding limit per client address and normalized email."""

    host_key = f"terrasatch:billing:checkout:ip:{_digest(client_host or 'unknown')}"
    email_key = f"terrasatch:billing:checkout:email:{_digest(email)}"
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    try:
        async with redis.pipeline(transaction=True) as pipeline:
            pipeline.incr(host_key)
            pipeline.expire(host_key, _WINDOW_SECONDS)
            pipeline.incr(email_key)
            pipeline.expire(email_key, _WINDOW_SECONDS)
            result = await pipeline.execute()
    except RedisError as error:
        raise ProviderUnavailable("Billing request limiter is unavailable") from error
    finally:
        await redis.aclose()

    ip_count = int(result[0])
    email_count = int(result[2])
    if ip_count > _IP_LIMIT or email_count > _EMAIL_LIMIT:
        raise RateLimitExceeded(
            "Too many billing attempts. Try again later.",
            details={"retry_after_seconds": _WINDOW_SECONDS},
        )
