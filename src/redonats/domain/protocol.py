"""Pure Centrifugo protocol handling: frame building and parsing.

Every function here is deterministic and side-effect free, so the
protocol can be unit-tested without network or mocking.
"""

import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

from redonats.domain.errors import ProtocolError
from redonats.domain.models import Donation


def donation_channel(client_id: str) -> str:
    """Return the DonationAlerts donation channel for a client id."""
    return f"$alerts:donation_{client_id}"


def build_connect_frame(connection_token: str) -> dict[str, object]:
    """Build the Centrifugo connect frame for a connection token."""
    return {"params": {"token": connection_token}, "id": 1}


def build_subscribe_frame(channel: str, token: str) -> dict[str, object]:
    """Build the Centrifugo subscribe frame for a channel."""
    return {"params": {"channel": channel, "token": token}, "method": 1, "id": 2}


def require_success(frame: Mapping[str, object]) -> None:
    """Raise ProtocolError if a gateway frame reports an error.

    Args:
        frame: a decoded Centrifugo response frame.

    Raises:
        ProtocolError: if the frame carries an ``error`` field.
    """
    if "error" in frame:
        raise ProtocolError(f"gateway error: {frame['error']!r}")


def parse_welcome(frame: Mapping[str, object]) -> str:
    """Extract the client uid from the connect handshake response.

    Raises:
        ProtocolError: if the frame has no usable client uid.
    """
    result = frame.get("result")
    if not isinstance(result, Mapping):
        raise ProtocolError(f"connect frame has no result object: {frame!r}")
    client = result.get("client")
    if not isinstance(client, str):
        raise ProtocolError(f"connect frame has no client uid: {frame!r}")
    return client


def extract_connection_token(payload: Mapping[str, object]) -> str:
    """Extract the socket connection token from the oauth response.

    Raises:
        ProtocolError: if the token is missing.
    """
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise ProtocolError(f"oauth response has no data object: {payload!r}")
    token = data.get("socket_connection_token")
    if not isinstance(token, str):
        raise ProtocolError(
            f"oauth response has no socket_connection_token: {payload!r}"
        )
    return token


def extract_subscription_token(payload: Mapping[str, object]) -> str:
    """Extract the first channel token from the subscribe response.

    Raises:
        ProtocolError: if no channel token is present.
    """
    channels = payload.get("channels")
    if not isinstance(channels, list) or not channels:
        raise ProtocolError(f"subscribe response has no channels: {payload!r}")
    channel = channels[0]
    token = channel.get("token") if isinstance(channel, Mapping) else None
    if not isinstance(token, str):
        raise ProtocolError(f"subscribe response has no token: {payload!r}")
    return token


def parse_push(envelope: Mapping[str, object]) -> Donation:
    """Extract a Donation from a Centrifugo push envelope.

    The envelope carries the donation as ``push.data``: either a JSON
    string or an already-decoded object, depending on gateway version.

    Raises:
        ProtocolError: if the envelope or the donation payload is malformed.
    """
    push = envelope.get("push")
    if not isinstance(push, Mapping):
        raise ProtocolError(f"push envelope has no push object: {envelope!r}")
    data = push.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ProtocolError(
                f"donation payload is not valid JSON: {data!r}"
            ) from exc
    if not isinstance(data, Mapping):
        raise ProtocolError(f"donation payload is not an object: {data!r}")
    return parse_donation(data)


def is_push_frame(frame: Mapping[str, object]) -> bool:
    """Return True if the frame is a channel push rather than a command result.

    The gateway also delivers command responses (e.g. the subscribe
    confirmation) as channel messages; those must be ignored.
    """
    return "push" in frame


def parse_donation(data: Mapping[str, object]) -> Donation:
    """Map a raw donation object onto a Donation.

    Raises:
        ProtocolError: if required fields are missing or of the wrong type.
    """
    try:
        return Donation(
            id=int(data["id"]),
            amount=Decimal(str(data["amount"])),
            currency=str(data["currency"]),
            username=str(data["username"]),
            message=str(data.get("message") or ""),
            created_at=str(data["created_at"]),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise ProtocolError(
            f"donation payload misses required fields: {data!r}"
        ) from exc
