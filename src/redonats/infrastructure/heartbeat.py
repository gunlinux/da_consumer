"""Heartbeat file writing (infrastructure boundary).

The heartbeat lets a container healthcheck distinguish a live event
loop from a wedged process.
"""

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def write_heartbeat(path: str) -> None:
    """Write the current epoch time to the heartbeat file.

    Failures are logged, never raised: an unwritable heartbeat must not
    take the listener down.
    """
    try:
        Path(path).write_text(f"{time.time():.0f}\n", encoding="ascii")
    except OSError as exc:
        logger.warning("could not write heartbeat %s: %s", path, exc)
