"""Composition root: wire configuration, logging and signal handling."""

import asyncio
import os
import signal
from collections.abc import Callable, Mapping

from dotenv import load_dotenv

from redonats.application.gateway import Gateway
from redonats.application.publisher import (
    Broker,
    ensure_queue,
    make_broker,
    make_push_handler,
)
from redonats.application.service import Stats, run
from redonats.domain.errors import ConfigError
from redonats.domain.models import Settings
from redonats.infrastructure.config import load_settings
from redonats.infrastructure.gateway import AiohttpGateway
from redonats.infrastructure.logging_setup import configure_logging


def main() -> None:
    """Entry point: load configuration and start listening."""
    load_dotenv()
    run_cli(os.environ, AiohttpGateway())


def run_cli(env: Mapping[str, str | None], gateway: Gateway) -> None:
    """Synchronous CLI orchestration: load settings, then run the listener.

    Args:
        env: environment mapping, e.g. ``os.environ``.
        gateway: gateway adapter implementing the ``Gateway`` protocol.

    Raises:
        SystemExit: 2 on configuration errors, 1 on broker connect failure.
    """
    try:
        settings = load_settings(env)
        configure_logging(settings.log_level)
    except ConfigError as exc:
        print(f"configuration error: {exc}", flush=True)
        raise SystemExit(2) from exc
    asyncio.run(_async_main(settings, gateway))


async def _async_main(
    settings: Settings,
    gateway: Gateway,
    *,
    broker_factory: Callable[[Settings], Broker] = make_broker,
    signals: tuple[signal.Signals, ...] = (signal.SIGTERM, signal.SIGINT),
    shutdown: asyncio.Event | None = None,
) -> None:
    """Run the listener: broker startup, signal handling and the stream loop.

    Args:
        settings: runtime settings.
        gateway: gateway adapter implementing the ``Gateway`` protocol.
        broker_factory: builds the broker; injectable for tests.
        signals: OS signals requesting shutdown; empty disables them.
        shutdown: shutdown event; created and wired to ``signals`` when omitted.
    """
    broker = broker_factory(settings)
    try:
        await broker.start()
    except Exception as exc:
        print(f"could not connect to RabbitMQ: {exc}", flush=True)
        raise SystemExit(1) from exc
    loop = asyncio.get_running_loop()
    installed = shutdown is None
    try:
        try:
            await ensure_queue(broker, settings)
        except Exception as exc:
            print(f"could not declare queue: {exc}", flush=True)
            raise SystemExit(1) from exc
        event = shutdown if shutdown is not None else asyncio.Event()
        if installed:
            for sig in signals:
                loop.add_signal_handler(sig, event.set)
        stats = Stats()
        try:
            await run(
                settings,
                gateway,
                event,
                on_push=make_push_handler(broker, settings, stats=stats),
                stats=stats,
            )
        finally:
            if installed:
                for sig in signals:
                    loop.remove_signal_handler(sig)
    finally:
        await broker.stop()
