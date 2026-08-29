"""FastStream (RabbitMQ) publisher for donations.

Mirrors youtube_consumer's publisher: the durable queue is declared at
startup and every donation is published to it as JSON.
"""

import logging

from faststream.rabbit import RabbitBroker, RabbitQueue
from pydantic import BaseModel

from redonats.application.gateway import PushHandler
from redonats.application.service import log_donation
from redonats.domain.models import Donation, Settings

logger = logging.getLogger(__name__)


class DonationCreate(BaseModel):
    """Queue payload contract for a donation event."""

    id: int
    amount: float
    currency: str
    username: str
    message: str
    created_at: str


def make_broker(settings: Settings) -> RabbitBroker:
    """Build the RabbitMQ broker, mirroring youtube_consumer conventions."""
    return RabbitBroker(
        url=settings.amqp_dsn,
        reconnect_interval=settings.amqp_reconnect_delay,
        logger=logger,
    )


async def ensure_queue(broker: RabbitBroker, settings: Settings) -> None:
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
    broker: RabbitBroker, donation: Donation, settings: Settings
) -> None:
    """Publish one donation to the queue as JSON."""
    payload = to_donation_create(donation)
    await broker.publish(payload.model_dump(mode="json"), queue=settings.amqp_queue)
    logger.info("published donation id=%d from %s", payload.id, payload.username)


def make_push_handler(broker: RabbitBroker, settings: Settings) -> PushHandler:
    """Build the donation sink: log the donation and publish it to RabbitMQ.

    Publish failures are logged and swallowed so a broker hiccup cannot
    tear down the donation stream — the donation is still in the logs.
    """

    async def handler(donation: Donation) -> None:
        log_donation(donation)
        try:
            await publish_donation(broker, donation, settings)
        except Exception:
            logger.exception("failed to publish donation id=%d", donation.id)

    return handler
