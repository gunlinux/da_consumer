"""Gateway abstraction: the DonationAlerts adapter surface.

The application layer depends on this protocol; the aiohttp adapter in
``redonats.infrastructure.gateway`` implements it, and tests inject
fakes. This keeps the reconnect loop testable without network.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from redonats.domain.models import Donation, Settings

PushHandler = Callable[[Donation], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class StreamOutcome:
    """How a single stream attempt ended.

    Attributes:
        connected: whether the channel was reached (handshake and
            subscription succeeded) before the attempt ended.
        duration: wall-clock seconds the attempt ran.
    """

    connected: bool
    duration: float


class Gateway(Protocol):
    """The DonationAlerts gateway as seen by the application layer."""

    async def connect(self) -> None:
        """Open shared resources (e.g. an HTTP session)."""

    async def close(self) -> None:
        """Release shared resources."""

    async def run_stream(
        self, settings: Settings, on_push: PushHandler
    ) -> StreamOutcome:
        """Run one stream attempt, delivering donations to ``on_push``."""
