"""Heartbeat file writing (infrastructure boundary).

The heartbeat lets a container healthcheck distinguish a live event
loop from a wedged process. The file is rewritten on a fixed cadence,
so its mtime is the liveness signal; the JSON content carries counters
for observability.
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def write_heartbeat(path: str, stats: dict[str, object] | None = None) -> None:
    """Write heartbeat JSON to ``path`` with the current epoch time.

    Args:
        path: heartbeat file path.
        stats: optional flat mapping of counters merged into the payload.

    Failures are logged, never raised: an unwritable heartbeat must not
    take the listener down.
    """
    payload = {"ts": time.time()}
    if stats:
        payload.update(stats)
    try:
        Path(path).write_text(json.dumps(payload), encoding="ascii")
    except OSError as exc:
        logger.warning("could not write heartbeat %s: %s", path, exc)
