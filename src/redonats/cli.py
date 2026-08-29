"""Composition root: wire configuration, logging and signal handling."""

import asyncio
import os
import signal

from dotenv import load_dotenv

from redonats.application.gateway import Gateway
from redonats.application.publisher import ensure_queue, make_broker, make_push_handler
from redonats.application.service import run
from redonats.domain.errors import ConfigError
from redonats.domain.models import Settings
from redonats.infrastructure.config import load_settings
from redonats.infrastructure.gateway import AiohttpGateway
from redonats.infrastructure.logging_setup import configure_logging


def main() -> None:
    """Entry point: load configuration and start listening."""
    load_dotenv()
    try:
        settings = load_settings(os.environ)
        configure_logging(settings.log_level)
    except ConfigError as exc:
        print(f"configuration error: {exc}", flush=True)
        raise SystemExit(2) from exc
    asyncio.run(_async_main(settings, AiohttpGateway()))


async def _async_main(settings: Settings, gateway: Gateway) -> None:
    """Run the listener: broker startup, signal handling and the stream loop."""
    broker = make_broker(settings)
    try:
        await broker.start()
    except Exception as exc:
        print(f"could not connect to RabbitMQ: {exc}", flush=True)
        raise SystemExit(1) from exc
    try:
        await ensure_queue(broker, settings)
        shutdown = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, shutdown.set)
        try:
            await run(
                settings,
                gateway,
                shutdown,
                on_push=make_push_handler(broker, settings),
            )
        finally:
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(sig)
    finally:
        await broker.stop()
