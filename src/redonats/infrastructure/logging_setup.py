"""Logging configuration (infrastructure boundary)."""

import logging

from redonats.domain.errors import ConfigError

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str) -> None:
    """Configure the root logger with a key=value message format.

    Args:
        level: log level name (e.g. "INFO", "DEBUG").

    Raises:
        ConfigError: if ``level`` is not a valid logging level name.
    """
    numeric = getattr(logging, level.upper(), None)
    if not isinstance(numeric, int):
        raise ConfigError(f"unknown log level: {level!r}")
    logging.basicConfig(level=numeric, format=_LOG_FORMAT, force=True)
