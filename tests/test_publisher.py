import logging

import pytest

import redonats.application.publisher as publisher
from redonats.application.publisher import (
    _publish_with_retry,
    ensure_queue,
    make_broker,
    make_push_handler,
    publish_donation,
    to_donation_create,
)
from redonats.application.service import Stats
from redonats.domain.models import Donation, Settings


def make_donation(**overrides) -> Donation:
    base = {
        "id": 1,
        "amount": 12.5,
        "currency": "RUB",
        "username": "alice",
        "message": "hello",
        "created_at": "2026-08-29T10:00:00Z",
    }
    base.update(overrides)
    return Donation(**base)


def make_settings(**overrides) -> Settings:
    base = {
        "client_id": "42",
        "access_token": "secret",
        "amqp_dsn": "amqp://localhost:5672",
    }
    base.update(overrides)
    return Settings(**base)


class FakeBroker:
    """Duck-typed RabbitBroker stand-in recording publish/declare calls."""

    def __init__(self) -> None:
        self.published: list[tuple[dict, str, dict]] = []
        self.declared: list = []

    async def publish(self, message, *, queue=None, **kwargs) -> None:
        self.published.append((message, queue, kwargs))

    async def declare_queue(self, queue) -> None:
        self.declared.append(queue)


def test_to_donation_create_maps_fields() -> None:
    create = to_donation_create(make_donation())
    assert create.id == 1
    assert create.amount == 12.5
    assert create.currency == "RUB"
    assert create.username == "alice"
    assert create.message == "hello"
    assert create.created_at == "2026-08-29T10:00:00Z"


async def test_publish_donation_publishes_persistent_json_payload() -> None:
    broker = FakeBroker()
    settings = make_settings()

    await publish_donation(broker, make_donation(), settings.amqp_queue)

    assert len(broker.published) == 1
    payload, queue, kwargs = broker.published[0]
    assert queue == "donations"
    assert kwargs["persist"] is True
    assert payload == {
        "id": 1,
        "amount": 12.5,
        "currency": "RUB",
        "username": "alice",
        "message": "hello",
        "created_at": "2026-08-29T10:00:00Z",
    }
    assert isinstance(payload["amount"], (int, float))


async def test_publish_with_retry_does_not_retry_non_transient_error() -> None:
    class NonTransientBroker:
        def __init__(self) -> None:
            self.calls = 0

        async def publish(self, message, *, queue=None, **kwargs) -> None:
            self.calls += 1
            raise ValueError("cannot serialize")

    broker = NonTransientBroker()

    with pytest.raises(ValueError):
        await _publish_with_retry(broker, make_donation(), make_settings())

    assert broker.calls == 1


async def test_ensure_queue_declares_durable_queue() -> None:
    broker = FakeBroker()
    settings = make_settings()

    await ensure_queue(broker, settings)

    assert len(broker.declared) == 1
    queue = broker.declared[0]
    assert queue.name == "donations"
    assert queue.durable is True


def test_make_broker_uses_settings(monkeypatch) -> None:
    captured: dict = {}

    class FakeRabbitBroker:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(publisher, "RabbitBroker", FakeRabbitBroker)

    make_broker(make_settings(amqp_reconnect_delay=7.0))

    assert captured["url"] == "amqp://localhost:5672"
    assert captured["reconnect_interval"] == 7.0


async def test_make_push_handler_logs_and_publishes(caplog) -> None:
    broker = FakeBroker()
    settings = make_settings()
    handler = make_push_handler(broker, settings)

    with caplog.at_level(logging.INFO):
        await handler(make_donation())

    assert len(broker.published) == 1
    assert "event=donation" in caplog.text
    assert "published donation id=1" in caplog.text


async def test_make_push_handler_retries_then_succeeds() -> None:
    class FlakyBroker:
        def __init__(self) -> None:
            self.calls = 0

        async def publish(self, message, *, queue=None, **kwargs) -> None:
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("broker down")

    stats = Stats()
    handler = make_push_handler(FlakyBroker(), make_settings(), stats=stats)

    await handler(make_donation())

    assert stats.publish_failures == 0
    assert stats.donations == 1


async def test_make_push_handler_records_failure_after_retries(caplog) -> None:
    class ExplodingBroker:
        async def publish(self, message, *, queue=None, **kwargs) -> None:
            raise RuntimeError("broker down")

    stats = Stats()
    handler = make_push_handler(ExplodingBroker(), make_settings(), stats=stats)

    await handler(make_donation())

    assert stats.publish_failures == 1
    assert "failed to publish donation id=1" in caplog.text
    assert "RuntimeError: broker down" in caplog.text


async def test_make_push_handler_survives_publish_failure(caplog) -> None:
    class ExplodingBroker:
        async def publish(self, message, *, queue=None, **kwargs) -> None:
            raise RuntimeError("broker down")

    settings = make_settings()
    handler = make_push_handler(ExplodingBroker(), settings)

    await handler(make_donation())

    assert "failed to publish donation id=1" in caplog.text
