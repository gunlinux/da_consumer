"""Composition root tests: exit codes, startup sequence and injectable seams.

These tests never touch the network or RabbitMQ: the broker and gateway
are duck-typed fakes and no OS signal handlers are ever registered.
"""

import asyncio
from pathlib import Path

import pytest

from redonats.application.gateway import StreamOutcome
from redonats.cli import _async_main, run_cli
from redonats.domain.models import Settings


class FakeBroker:
    """Duck-typed broker recording lifecycle and declare calls."""

    def __init__(self, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.started = 0
        self.stopped = 0
        self.declared: list[str] = []

    async def start(self) -> None:
        if self.fail_start:
            raise ConnectionError("broker unreachable")
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    async def declare_queue(self, queue) -> None:
        self.declared.append(queue.name)

    async def publish(self, message, *, queue=None, **kwargs) -> None:
        pass


class FailDeclareBroker(FakeBroker):
    """Broker double whose queue declaration fails."""

    async def declare_queue(self, queue) -> None:
        raise RuntimeError("queue exists")


class FakeGateway:
    """Gateway double: reports successful streams, never touches I/O."""

    def __init__(self) -> None:
        self.connected = 0
        self.closed = 0
        self.streams = 0

    async def connect(self) -> None:
        self.connected += 1

    async def close(self) -> None:
        self.closed += 1

    async def run_stream(self, settings, on_push) -> StreamOutcome:
        self.streams += 1
        return StreamOutcome(connected=True, duration=0.0)


class CloseRaisesGateway(FakeGateway):
    """Gateway double whose teardown fails."""

    async def close(self) -> None:
        raise RuntimeError("close failed")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        client_id="42",
        access_token="secret",
        heartbeat_path=str(tmp_path / "heartbeat"),
        amqp_dsn="amqp://localhost:5672",
    )


async def _stop_after(shutdown: asyncio.Event, seconds: float) -> None:
    await asyncio.sleep(seconds)
    shutdown.set()


def test_run_cli_exits_2_on_missing_env(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        run_cli({}, FakeGateway())
    assert excinfo.value.code == 2
    assert "configuration error" in capsys.readouterr().out


def test_run_cli_exits_2_on_invalid_numbers(capsys) -> None:
    env = {
        "DA_USER_ID": "42",
        "DA_ACCESS_TOKEN": "secret",
        "AMQP_DSN": "amqp://localhost:5672",
        "DA_RECONNECT_MAX_DELAY": "not-a-number",
    }
    with pytest.raises(SystemExit) as excinfo:
        run_cli(env, FakeGateway())
    assert excinfo.value.code == 2
    assert "configuration error" in capsys.readouterr().out


async def test_async_main_exits_1_on_broker_failure(capsys) -> None:
    settings = Settings(
        client_id="42",
        access_token="secret",
        amqp_dsn="amqp://localhost:5672",
    )
    with pytest.raises(SystemExit) as excinfo:
        await _async_main(
            settings,
            FakeGateway(),
            broker_factory=lambda s: FakeBroker(fail_start=True),
            signals=(),
        )
    assert excinfo.value.code == 1
    assert "could not connect to RabbitMQ" in capsys.readouterr().out


async def test_async_main_exits_1_on_queue_declare_failure(capsys) -> None:
    settings = Settings(
        client_id="42",
        access_token="secret",
        amqp_dsn="amqp://localhost:5672",
    )
    with pytest.raises(SystemExit) as excinfo:
        await _async_main(
            settings,
            FakeGateway(),
            broker_factory=lambda s: FailDeclareBroker(),
            signals=(),
        )
    assert excinfo.value.code == 1
    assert "could not declare queue" in capsys.readouterr().out


async def test_async_main_runs_stream_until_shutdown(tmp_path, monkeypatch) -> None:
    broker = FakeBroker()
    gateway = FakeGateway()
    settings = make_settings(tmp_path)
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    registered: list[tuple] = []
    monkeypatch.setattr(
        loop, "add_signal_handler", lambda *args: registered.append(args)
    )
    monkeypatch.setattr(
        loop, "remove_signal_handler", lambda *args: registered.append(args)
    )
    stop_task = asyncio.create_task(_stop_after(shutdown, 0.05))

    await _async_main(
        settings,
        gateway,
        broker_factory=lambda s: broker,
        signals=(),
        shutdown=shutdown,
    )
    await stop_task

    assert broker.started == 1
    assert broker.stopped == 1
    assert broker.declared == ["donations"]
    assert gateway.connected == 1
    assert gateway.closed == 1
    assert gateway.streams >= 1
    assert registered == []


async def test_async_main_stops_broker_when_stream_fails(tmp_path) -> None:
    broker = FakeBroker()
    settings = make_settings(tmp_path)
    shutdown = asyncio.Event()
    stop_task = asyncio.create_task(_stop_after(shutdown, 0.05))

    with pytest.raises(RuntimeError):
        await _async_main(
            settings,
            CloseRaisesGateway(),
            broker_factory=lambda s: broker,
            signals=(),
            shutdown=shutdown,
        )
    await stop_task

    assert broker.started == 1
    assert broker.stopped == 1
