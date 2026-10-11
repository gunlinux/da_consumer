import asyncio
import contextlib
import json
import logging
from pathlib import Path

import pytest

from redonats.application.gateway import StreamOutcome
from redonats.application.service import (
    Stats,
    _heartbeat_loop,
    backoff_delay,
    log_donation,
    run,
    wait_until_shutdown,
)
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


class ConnectFailsGateway:
    """Gateway double whose connect() raises."""

    def __init__(self) -> None:
        self.closed = 0

    async def connect(self) -> None:
        raise RuntimeError("session boom")

    async def close(self) -> None:
        self.closed += 1

    async def run_stream(self, settings, on_push) -> StreamOutcome:
        raise AssertionError("must not run")


class ExplodingStreamGateway:
    """Gateway double whose stream attempts always raise."""

    def __init__(self) -> None:
        self.attempts = 0
        self.closed = 0

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        self.closed += 1

    async def run_stream(self, settings, on_push) -> StreamOutcome:
        self.attempts += 1
        raise RuntimeError("boom")


class ProgrammingErrorGateway:
    """Gateway double whose stream attempts raise a programming error."""

    def __init__(self) -> None:
        self.closed = 0

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        self.closed += 1

    async def run_stream(self, settings, on_push) -> StreamOutcome:
        raise TypeError("programming error")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        client_id="42",
        access_token="secret",
        heartbeat_path=str(tmp_path / "heartbeat"),
        amqp_dsn="amqp://localhost:5672",
    )


def _donation(**overrides) -> Donation:
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


def test_record_donation_sets_counters_and_timestamp() -> None:
    stats = Stats()
    stats.record_donation(1234.5)
    assert stats.donations == 1
    assert stats.last_donation_at == 1234.5


def test_record_publish_failure_increments() -> None:
    stats = Stats(publish_failures=2)
    stats.record_publish_failure()
    assert stats.publish_failures == 3


def test_record_publish_success_resets() -> None:
    stats = Stats(publish_failures=3)
    stats.record_publish_success()
    assert stats.publish_failures == 0


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
    donation = _donation()
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


async def test_backoff_grows_after_short_connected_streams(tmp_path) -> None:
    settings = _settings(tmp_path)
    gateway = FakeGateway([StreamOutcome(connected=True, duration=1.0)])
    shutdown = asyncio.Event()
    stop_task = asyncio.create_task(_stop_after(shutdown, 0.2))
    attempts: list[int] = []

    def recording_backoff(attempt: int, max_delay: float) -> float:
        attempts.append(attempt)
        return 0.001

    await run(settings, gateway, shutdown, backoff=recording_backoff)
    await stop_task

    assert len(attempts) >= 3
    assert attempts == list(range(len(attempts)))


async def test_backoff_resets_after_sustained_stream(tmp_path) -> None:
    settings = _settings(tmp_path)
    gateway = FakeGateway(
        [
            StreamOutcome(connected=True, duration=1.0),
            StreamOutcome(connected=True, duration=1.0),
            StreamOutcome(connected=True, duration=31.0),
        ]
    )
    shutdown = asyncio.Event()
    stop_task = asyncio.create_task(_stop_after(shutdown, 0.2))
    attempts: list[int] = []

    def recording_backoff(attempt: int, max_delay: float) -> float:
        attempts.append(attempt)
        return 0.001

    await run(settings, gateway, shutdown, backoff=recording_backoff)
    await stop_task

    # Two short streams grow the counter (0, 1); the sustained stream resets
    # it, so the backoff right after it is 0 again instead of 2.
    assert attempts[:3] == [0, 1, 0]
    assert attempts[3] == 1


async def test_connect_failure_cleans_up(tmp_path) -> None:
    settings = _settings(tmp_path)
    gateway = ConnectFailsGateway()
    shutdown = asyncio.Event()

    with pytest.raises(RuntimeError):
        await run(settings, gateway, shutdown)

    assert gateway.closed == 1
    assert not (tmp_path / "heartbeat").exists()


async def test_unexpected_gateway_error_continues_loop(tmp_path, caplog) -> None:
    settings = _settings(tmp_path)
    gateway = ExplodingStreamGateway()
    shutdown = asyncio.Event()
    stop_task = asyncio.create_task(_stop_after(shutdown, 0.2))

    await run(settings, gateway, shutdown, backoff=fast_backoff)
    await stop_task

    assert gateway.attempts >= 2
    assert gateway.closed == 1
    assert "unexpected gateway failure" in caplog.text


async def test_programming_error_propagates(tmp_path) -> None:
    settings = _settings(tmp_path)
    gateway = ProgrammingErrorGateway()
    shutdown = asyncio.Event()

    with pytest.raises(TypeError):
        await run(settings, gateway, shutdown)

    assert gateway.closed == 1


async def test_heartbeat_loop_writes_and_is_cancellable(tmp_path) -> None:
    path = str(tmp_path / "heartbeat")
    task = asyncio.create_task(_heartbeat_loop(path, interval=0.01))
    await asyncio.sleep(0.03)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert Path(path).exists()
    assert "ts" in json.loads(Path(path).read_text())


async def test_heartbeat_writes_stats(tmp_path) -> None:
    stats = Stats(donations=4, publish_failures=1)
    path = str(tmp_path / "heartbeat")
    task = asyncio.create_task(_heartbeat_loop(path, stats=stats, interval=3600))
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    payload = json.loads(Path(path).read_text())
    assert payload["donations"] == 4
    assert payload["publish_failures"] == 1


async def test_heartbeat_loop_logs_periodic_summary(tmp_path, caplog) -> None:
    stats = Stats(donations=3, publish_failures=2)
    path = str(tmp_path / "heartbeat")
    task = asyncio.create_task(_heartbeat_loop(path, stats=stats, interval=0.002))
    with caplog.at_level(logging.INFO):
        await asyncio.sleep(0.3)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert "health summary: donations=3 publish_failures=2" in caplog.text


async def test_log_donation_quotes_message(caplog) -> None:
    donation = _donation(message='hello world "quoted"')

    with caplog.at_level(logging.INFO):
        await log_donation(donation)

    line = caplog.text.strip().splitlines()[-1]
    message_part = line.split("message=", 1)[1]
    assert json.loads(message_part) == 'hello world "quoted"'
