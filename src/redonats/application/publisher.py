"""FastStream (RabbitMQ) publisher for donations.

Mirrors youtube_consumer's publisher: the durable queue is declared at
startup and every donation is published to it as a persistent JSON
message. Publish failures are retried a bounded number of times and
then logged so a broker hiccup cannot tear down the donation stream.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Protocol

from faststream.rabbit import RabbitBroker, RabbitQueue
from pydantic import BaseModel, field_serializer

from redonats.application.gateway import PushHandler
from redonats.application.service import Stats, log_donation
from redonats.domain.models import Donation, Settings

logger = logging.getLogger(__name__)

_PUBLISH_MAX_ATTEMPTS: int = 3
_PUBLISH_RETRY_DELAYS: tuple[float, ...] = (0.2, 0.5)


class DonationCreate(BaseModel):
    """Queue payload contract for a donation event."""

    id: int
    amount: Decimal
    currency: str
    username: str
    message: str
    created_at: str

    @field_serializer("amount")
    def _serialize_amount(self, amount: Decimal) -> float:
        """Keep the wire contract: ``amount`` stays a JSON number."""
        return float(amount)


class Broker(Protocol):
    """Structural seam for the RabbitMQ broker, satisfied by ``RabbitBroker``."""

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def declare_queue(self, queue: RabbitQueue) -> None: ...

    async def publish(
        self, message: Any, *, queue: str, persist: bool = False
    ) -> None: ...


def make_broker(settings: Settings) -> RabbitBroker:
    """Build the RabbitMQ broker, mirroring youtube_consumer conventions."""
    return RabbitBroker(
        url=settings.amqp_dsn,
        reconnect_interval=settings.amqp_reconnect_delay,
        logger=logger,
    )


async def ensure_queue(broker: Broker, settings: Settings) -> None:
    """Declare the durable queue so publishes are never silently dropped."""
    await broker.declare_queue(RabbitQueue(settings.amqp_queue, durable=True))


def to_donation_create(donation: Donation) -> DonationCreate:
    """Map a Donation onto the queue payload schema."""
    return DonationCreate(
        id=donation.id,
        amount=donation.amount,
        currency=donation.currency,
        username=donation.username,
        message=donation.message,
        created_at=donation.created_at,
    )


async def publish_donation(
    broker: Broker, donation: Donation, settings: Settings
) -> None:
    """Publish one donation to the queue as a persistent message."""
    payload = to_donation_create(donation)
    await broker.publish(
        payload.model_dump(mode="json"),
        queue=settings.amqp_queue,
        persist=True,
    )
    logger.info("published donation id=%d from %s", payload.id, payload.username)


async def _publish_with_retry(
    broker: Broker, donation: Donation, settings: Settings
) -> None:
    """Publish with bounded retries; raises once the attempts are exhausted."""
    for attempt in range(_PUBLISH_MAX_ATTEMPTS):
        try:
            await publish_donation(broker, donation, settings)
            return
        except Exception:
            if attempt == _PUBLISH_MAX_ATTEMPTS - 1:
                raise
            delay = _PUBLISH_RETRY_DELAYS[attempt]
            logger.warning(
                "publish attempt %d failed for donation id=%d, retrying in %.1fs",
                attempt + 1,
                donation.id,
                delay,
                exc_info=True,
            )
            await asyncio.sleep(delay)


def make_push_handler(
    broker: Broker,
    settings: Settings,
    stats: Stats | None = None,
) -> PushHandler:
    """Build the donation sink: log the donation and publish it to RabbitMQ.

    Publish failures are retried a bounded number of times and then
    logged; they never tear down the donation stream — the donation is
    still in the logs and the failure is counted in ``stats``.
    """

    async def handler(donation: Donation) -> None:
        log_donation(donation)
        if stats is not None:
            stats.record_donation()
        try:
            await _publish_with_retry(broker, donation, settings)
        except Exception:
            logger.exception(
                "failed to publish donation id=%d after %d attempts",
                donation.id,
                _PUBLISH_MAX_ATTEMPTS,
            )
            if stats is not None:
                stats.publish_failures += 1
        else:
            if stats is not None:
                stats.publish_failures = 0

    return handler
