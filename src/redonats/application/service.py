"""Donation stream orchestration: reconnect loop and lifecycle.

The application layer is deliberately thin: it owns the retry policy,
the shutdown handling and the heartbeat, and delegates all protocol and
I/O concerns to the injected ``Gateway``.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable

from redonats.application.gateway import Gateway, PushHandler, StreamOutcome
from redonats.domain.models import Donation, Settings
from redonats.infrastructure.heartbeat import write_heartbeat

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL: float = 15.0
BACKOFF_BASE: float = 1.0


def log_donation(donation: Donation) -> None:
    """Log a donation as a structured key=value line."""
    logger.info(
        "event=donation id=%d user=%s amount=%.2f currency=%s created_at=%s message=%s",
        donation.id,
        donation.username,
        donation.amount,
        donation.currency,
        donation.created_at,
        donation.message,
    )


async def _log_only(donation: Donation) -> None:
    """Default sink: log the donation."""
    log_donation(donation)


def backoff_delay(attempt: int, max_delay: float) -> float:
    """Exponential backoff delay for a failed attempt.

    Args:
        attempt: number of consecutive failed attempts (0-based).
        max_delay: upper bound on the returned delay in seconds.

    Returns:
        ``min(max_delay, BACKOFF_BASE * 2 ** attempt)`` seconds.
    """
    return min(max_delay, BACKOFF_BASE * 2**attempt)


async def wait_until_shutdown(shutdown: asyncio.Event, timeout: float) -> bool:
    """Wait up to ``timeout`` seconds for shutdown.

    Returns:
        True if shutdown was requested before the timeout elapsed.
    """
    try:
        await asyncio.wait_for(shutdown.wait(), timeout=timeout)
    except TimeoutError:
        return False
    return True


async def _heartbeat_loop(path: str, interval: float = HEARTBEAT_INTERVAL) -> None:
    """Write the heartbeat file every ``interval`` seconds until cancelled."""
    while True:
        write_heartbeat(path)
        await asyncio.sleep(interval)


async def run(
    settings: Settings,
    gateway: Gateway,
    shutdown: asyncio.Event,
    on_push: PushHandler = _log_only,
    backoff: Callable[[int, float], float] = backoff_delay,
) -> None:
    """Run the donation stream until shutdown, reconnecting with backoff.

    Args:
        settings: runtime settings.
        gateway: gateway adapter implementing the ``Gateway`` protocol.
        shutdown: set to request a clean stop.
        on_push: sink receiving each parsed donation.
        backoff: delay function for reconnect attempts (injectable for tests).
    """
    logger.info("starting donation listener (client_id=%s)", settings.client_id)
    heartbeat_task = asyncio.create_task(_heartbeat_loop(settings.heartbeat_path))
    attempt = 0
    await gateway.connect()
    try:
        while not shutdown.is_set():
            try:
                outcome = await gateway.run_stream(settings, on_push)
            except Exception:
                logger.exception("unexpected gateway failure")
                outcome = StreamOutcome(connected=False, duration=0.0)
            if outcome.connected:
                attempt = 0
            logger.info(
                "stream attempt ended (connected=%s, duration=%.1fs)",
                outcome.connected,
                outcome.duration,
            )
            if shutdown.is_set():
                break
            delay = backoff(attempt, settings.reconnect_max_delay)
            logger.info("reconnecting in %.1fs (attempt %d)", delay, attempt + 1)
            if await wait_until_shutdown(shutdown, delay):
                break
            attempt += 1
    finally:
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        await gateway.close()
        logger.info("donation listener stopped")
