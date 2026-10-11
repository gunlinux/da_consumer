"""Immutable domain models."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

API_BASE: Final = "https://www.donationalerts.com/api/v1"
WS_URL: Final = "wss://centrifugo.donationalerts.com/connection/websocket"
HEARTBEAT_PATH: Final = "/tmp/redonats.heartbeat"


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings assembled from environment variables."""

    client_id: str
    access_token: str
    api_base: str = API_BASE
    ws_url: str = WS_URL
    log_level: str = "INFO"
    reconnect_max_delay: float = 30.0
    heartbeat_path: str = HEARTBEAT_PATH
    amqp_dsn: str = ""
    amqp_queue: str = "donations"
    amqp_reconnect_delay: float = 5.0


@dataclass(frozen=True, slots=True)
class Donation:
    """A single donation event."""

    id: int
    amount: Decimal
    currency: str
    username: str
    message: str
    created_at: str

    def __post_init__(self) -> None:
        # Normalize float inputs through a decimal string so money values
        # never carry binary floating-point artifacts.
        object.__setattr__(self, "amount", Decimal(str(self.amount)))
