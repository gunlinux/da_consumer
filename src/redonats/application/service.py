"""Donation stream orchestration: reconnect loop and lifecycle.

The application layer is deliberately thin: it owns the retry policy,
the shutdown handling and the heartbeat, and delegates all protocol and
I/O concerns to the injected ``Gateway``.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from redonats.application.gateway import Gateway, PushHandler, StreamOutcome
from redonats.domain.models import Donation, Settings
from redonats.infrastructure.heartbeat import write_heartbeat

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL: float = 15.0
BACKOFF_BASE: float = 1.0
MIN_STREAM_DURATION: float = 30.0
HEARTBEAT_SUMMARY_TICKS: int = 60
# Transport-level failures the reconnect loop tolerates. Expected gateway
# failures (timeouts, HTTP errors, protocol errors) are already folded into
# StreamOutcome by the gateway; these are the unexpected transport errors
# that can still surface (dropped socket, closed event loop). Programming
# errors (TypeError, ValueError, ...) propagate and fail fast instead.
_GATEWAY_TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (OSError, RuntimeError)


@dataclass
class Stats:
    """Mutable counters shared between the push handler and the heartbeat loop.

    Deliberately not frozen: this is the one piece of mutable shared
    state in the application, updated by the publisher handler and read
    by the heartbeat writer.
    """

    donations: int = 0
    publish_failures: int = 0
    last_donation_at: float | None = None

    def record_donation(self, now: float) -> None:
        """Count a received donation and stamp its arrival time."""
        self.donations += 1
        self.last_donation_at = now

    def record_publish_failure(self) -> None:
        """Count a publish that failed after all retries."""
        self.publish_failures += 1

    def record_publish_success(self) -> None:
        """Reset the consecutive publish-failure counter after a success."""
        self.publish_failures = 0


def _stats_payload(stats: Stats | None) -> dict[str, object]:
    """Render the counters as a flat mapping for the heartbeat writer."""
    if stats is None:
        return {}
    return {
        "donations": stats.donations,
        "publish_failures": stats.publish_failures,
        "last_donation_at": stats.last_donation_at,
    }


async def log_donation(donation: Donation) -> None:
    """Log a donation as a structured key=value line.

    The message is JSON-encoded so whitespace or quotes in the free text
    cannot break line-based parsing of the log.
    """
    logger.info(
        "event=donation id=%d user=%s amount=%s currency=%s created_at=%s message=%s",
        donation.id,
        donation.username,
        donation.amount,
        donation.currency,
        donation.created_at,
        json.dumps(donation.message, ensure_ascii=False),
    )


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


async def _heartbeat_loop(
    path: str,
    stats: Stats | None = None,
    interval: float = HEARTBEAT_INTERVAL,
) -> None:
    """Write the heartbeat file every ``interval`` seconds until cancelled.

    Every ``HEARTBEAT_SUMMARY_TICKS`` ticks a summary of the counters is
    logged so long-running outages become visible in the logs.
    """
    tick = 0
    while True:
        write_heartbeat(path, _stats_payload(stats))
        tick += 1
        if stats is not None and tick % HEARTBEAT_SUMMARY_TICKS == 0:
            logger.info(
                "health summary: donations=%d publish_failures=%d",
                stats.donations,
                stats.publish_failures,
            )
        await asyncio.sleep(interval)


async def run(
    settings: Settings,
    gateway: Gateway,
    shutdown: asyncio.Event,
    on_push: PushHandler = log_donation,
    backoff: Callable[[int, float], float] = backoff_delay,
    stats: Stats | None = None,
) -> None:
    """Run the donation stream until shutdown, reconnecting with backoff.

    Args:
        settings: runtime settings.
        gateway: gateway adapter implementing the ``Gateway`` protocol.
        shutdown: set to request a clean stop.
        on_push: sink receiving each parsed donation.
        backoff: delay function for reconnect attempts (injectable for tests).
        stats: shared counters written to the heartbeat and the summary.
    """
    logger.info("starting donation listener (client_id=%s)", settings.client_id)
    attempt = 0
    heartbeat_task: asyncio.Task[None] | None = None
    try:
        await gateway.connect()
        heartbeat_task = asyncio.create_task(
            _heartbeat_loop(settings.heartbeat_path, stats)
        )
        while not shutdown.is_set():
            try:
                outcome = await gateway.run_stream(settings, on_push)
            except _GATEWAY_TRANSIENT_ERRORS:
                logger.exception("unexpected gateway failure")
                outcome = StreamOutcome(connected=False, duration=0.0)
            if outcome.connected and outcome.duration >= MIN_STREAM_DURATION:
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
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
        await gateway.close()
        logger.info("donation listener stopped")
