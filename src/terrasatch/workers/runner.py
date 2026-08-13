"""Minimal, supervised worker process foundation."""

from __future__ import annotations

import asyncio
import signal

import structlog
from redis.asyncio import Redis

from terrasatch.config import Settings
from terrasatch.observability.logging import configure_logging

logger = structlog.get_logger(__name__)


async def _publish_heartbeat(settings: Settings, shutdown_requested: asyncio.Event) -> None:
    """Publish an expiring worker heartbeat while the supervised process is alive."""

    client = Redis.from_url(str(settings.redis_url), socket_connect_timeout=2, socket_timeout=2)
    try:
        while not shutdown_requested.is_set():
            await client.set("terrasatch:worker:heartbeat", settings.deployment_name, ex=45)
            try:
                await asyncio.wait_for(shutdown_requested.wait(), timeout=15)
            except TimeoutError:
                continue
    finally:
        await client.aclose()


async def run_worker(settings: Settings) -> None:
    """Run the worker supervisor until a supported termination signal arrives.

    Task registration is deliberately centralized here so later transcription,
    intelligence, webhook, and retention tasks share one supervised process.
    """

    configure_logging(
        level=settings.log_level,
        json_output=settings.log_format.lower() == "json",
    )
    shutdown_requested = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        shutdown_requested.set()

    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(shutdown_signal, request_shutdown)
        except NotImplementedError:
            signal.signal(shutdown_signal, lambda _signal, _frame: request_shutdown())

    logger.info(
        "worker.started",
        environment=settings.environment.value,
        deployment=settings.deployment_name,
    )
    heartbeat_task = asyncio.create_task(_publish_heartbeat(settings, shutdown_requested))
    await shutdown_requested.wait()
    await heartbeat_task
    logger.info("worker.stopped")