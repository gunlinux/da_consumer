import asyncio
from pathlib import Path

from redonats.application.gateway import StreamOutcome
from redonats.application.service import backoff_delay, run, wait_until_shutdown
from redonats.domain.models import Donation, Settings


def fast_backoff(attempt: int, max_delay: float) -> float:
    """Backoff that returns instantly, keeping tests fast and deterministic."""
    return 0.001


class FakeGateway:
    """Gateway double: replays outcomes and push batches, never touches I/O."""

    def __init__(
        self,
        outcomes: list[StreamOutcome],
        push_batches: list[list[Donation]] | None = None,
    ) -> None:
        self.outcomes = list(outcomes)
        self.push_batches = list(push_batches) if push_batches else []
        self.connected = 0
        self.closed = 0

    async def connect(self) -> None:
        self.connected += 1

    async def close(self) -> None:
        self.closed += 1

    async def run_stream(self, settings, on_push) -> StreamOutcome:
        if self.push_batches:
            for donation in self.push_batches.pop(0):
                await on_push(donation)
        if self.outcomes:
            return self.outcomes.pop(0)
        return StreamOutcome(connected=True, duration=0.0)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        client_id="42",
        access_token="secret",
        heartbeat_path=str(tmp_path / "heartbeat"),
        amqp_dsn="amqp://localhost:5672",
    )


async def _stop_after(shutdown: asyncio.Event, seconds: float) -> None:
    await asyncio.sleep(seconds)
    shutdown.set()


def test_backoff_delay_grows_and_caps() -> None:
    assert backoff_delay(0, 30.0) == 1.0
    assert backoff_delay(2, 30.0) == 4.0
    assert backoff_delay(10, 30.0) == 30.0


async def test_wait_until_shutdown_times_out() -> None:
    shutdown = asyncio.Event()
    assert await wait_until_shutdown(shutdown, 0.01) is False


async def test_wait_until_shutdown_returns_when_signaled() -> None:
    shutdown = asyncio.Event()
    shutdown.set()
    assert await wait_until_shutdown(shutdown, 10.0) is True


async def test_run_reconnects_until_shutdown(tmp_path) -> None:
    settings = _settings(tmp_path)
    gateway = FakeGateway(
        [
            StreamOutcome(connected=False, duration=0.1),
            StreamOutcome(connected=False, duration=0.2),
            StreamOutcome(connected=True, duration=3.0),
        ]
    )
    shutdown = asyncio.Event()
    stop_task = asyncio.create_task(_stop_after(shutdown, 0.2))

    await run(settings, gateway, shutdown, backoff=fast_backoff)
    await stop_task

    assert gateway.outcomes == []
    assert gateway.connected == 1
    assert gateway.closed == 1
    assert (tmp_path / "heartbeat").exists()


async def test_run_dispatches_donations_to_sink(tmp_path) -> None:
    settings = _settings(tmp_path)
    donation = Donation(
        id=1,
        amount=12.5,
        currency="RUB",
        username="alice",
        message="hello",
        created_at="2026-08-29T10:00:00Z",
    )
    gateway = FakeGateway(
        [StreamOutcome(connected=True, duration=1.0)],
        push_batches=[[donation]],
    )
    shutdown = asyncio.Event()
    stop_task = asyncio.create_task(_stop_after(shutdown, 0.1))
    received: list[Donation] = []

    async def sink(donation: Donation) -> None:
        received.append(donation)

    await run(
        settings,
        gateway,
        shutdown,
        on_push=sink,
        backoff=fast_backoff,
    )
    await stop_task

    assert received == [donation]
    assert gateway.closed == 1
