"""aiohttp-backed DonationAlerts gateway (infrastructure boundary).

This adapter owns all network I/O: the oauth token exchange, the
Centrifugo websocket handshake and the message drain. Parsing and frame
building stay in ``domain.protocol`` as pure functions; expected
failures are reported through ``StreamOutcome`` so the application
layer can apply its retry policy.
"""

import json
import logging
import time
from typing import cast

import aiohttp

from redonats.application.gateway import Gateway, PushHandler, StreamOutcome
from redonats.domain.errors import ProtocolError
from redonats.domain.models import Settings
from redonats.domain.protocol import (
    build_connect_frame,
    build_subscribe_frame,
    donation_channel,
    extract_connection_token,
    extract_subscription_token,
    is_push_frame,
    parse_push,
    parse_welcome,
    require_success,
)

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_SECONDS = 30.0
_WS_HEARTBEAT_SECONDS = 60.0


class AiohttpGateway(Gateway):
    """DonationAlerts gateway adapter backed by aiohttp."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        """Open the shared HTTP session."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
        )

    async def close(self) -> None:
        """Close the shared HTTP session, if open."""
        session, self._session = self._session, None
        if session is not None:
            await session.close()

    @property
    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("gateway is not connected")
        return self._session

    async def run_stream(
        self, settings: Settings, on_push: PushHandler
    ) -> StreamOutcome:
        """Run one stream attempt: token exchange, handshake, subscribe, drain.

        Returns:
            StreamOutcome describing whether the channel was reached and
            how long the attempt ran. Expected network, gateway and
            protocol failures are captured in the outcome; programming
            errors propagate.
        """
        started = time.monotonic()
        try:
            connection_token = await self._fetch_connection_token(settings)
            async with self._http.ws_connect(
                settings.ws_url, heartbeat=_WS_HEARTBEAT_SECONDS
            ) as ws:
                client_uid = await self._handshake(ws, connection_token)
                token = await self._create_subscription(settings, client_uid)
                await self._subscribe(ws, settings, token)
                await self._drain(ws, on_push)
        except (TimeoutError, aiohttp.ClientError, OSError, ProtocolError) as exc:
            logger.warning("stream attempt failed: %s", exc)
            return StreamOutcome(connected=False, duration=time.monotonic() - started)
        return StreamOutcome(connected=True, duration=time.monotonic() - started)

    async def _fetch_connection_token(self, settings: Settings) -> str:
        headers = {"Authorization": f"Bearer {settings.access_token}"}
        async with self._http.get(
            f"{settings.api_base}/user/oauth", headers=headers
        ) as response:
            response.raise_for_status()
            payload = await response.json()
        return extract_connection_token(payload)

    async def _handshake(
        self, ws: aiohttp.ClientWebSocketResponse, connection_token: str
    ) -> str:
        await ws.send_json(build_connect_frame(connection_token))
        welcome = await ws.receive_json()
        require_success(welcome)
        return parse_welcome(welcome)

    async def _create_subscription(self, settings: Settings, client_uid: str) -> str:
        headers = {"Authorization": f"Bearer {settings.access_token}"}
        body = {
            "channels": [donation_channel(settings.client_id)],
            "client": client_uid,
        }
        async with self._http.post(
            f"{settings.api_base}/centrifuge/subscribe", json=body, headers=headers
        ) as response:
            response.raise_for_status()
            payload = await response.json()
        return extract_subscription_token(payload)

    async def _subscribe(
        self, ws: aiohttp.ClientWebSocketResponse, settings: Settings, token: str
    ) -> None:
        frame = build_subscribe_frame(donation_channel(settings.client_id), token)
        await ws.send_json(frame)
        require_success(await ws.receive_json())

    async def _drain(
        self, ws: aiohttp.ClientWebSocketResponse, on_push: PushHandler
    ) -> None:
        async for message in ws:
            if message.type is aiohttp.WSMsgType.TEXT:
                await _handle_text(cast(str, message.data), on_push)
            elif message.type in (
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                return
            else:
                logger.debug("ignoring websocket message of type %s", message.type)


async def _handle_text(raw: str, on_push: PushHandler) -> None:
    """Parse a websocket frame and deliver the donation it carries.

    Command responses (e.g. the subscribe confirmation) and malformed
    frames are reported and skipped so a single bad message cannot tear
    down the listener.
    """
    try:
        frame = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("could not parse websocket frame: %r (%s)", raw, exc)
        return
    if not is_push_frame(frame):
        logger.debug("ignoring non-push frame: %s", raw.strip())
        return
    try:
        donation = parse_push(frame)
    except ProtocolError as exc:
        logger.warning("could not parse push: %r (%s)", raw, exc)
        return
    await on_push(donation)
