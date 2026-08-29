import json
import logging

import aiohttp

from redonats.domain.models import Donation, Settings
from redonats.infrastructure.gateway import AiohttpGateway, _handle_text


def _donation_frame() -> str:
    donation = {
        "id": "1",
        "amount": "12.5",
        "currency": "RUB",
        "username": "alice",
        "message": "hi",
        "created_at": "2026-08-29T10:00:00Z",
    }
    return json.dumps({"push": {"data": donation}})


async def test_handle_text_delivers_push() -> None:
    received: list[Donation] = []

    async def sink(donation: Donation) -> None:
        received.append(donation)

    await _handle_text(_donation_frame(), sink)
    assert received == [
        Donation(
            id=1,
            amount=12.5,
            currency="RUB",
            username="alice",
            message="hi",
            created_at="2026-08-29T10:00:00Z",
        )
    ]


async def test_handle_text_ignores_command_results(caplog) -> None:
    frame = (
        '{"result":{"type":1,"channel":"$alerts:donation_42",'
        '"data":{"info":{"user":"Client:14474"}}}}'
    )
    received: list[Donation] = []

    async def sink(donation: Donation) -> None:
        received.append(donation)

    with caplog.at_level(logging.DEBUG):
        await _handle_text(frame, sink)
    assert received == []
    assert "non-push frame" in caplog.text
    assert "could not parse push" not in caplog.text


async def test_handle_text_skips_malformed_frames(caplog) -> None:
    received: list[Donation] = []

    async def sink(donation: Donation) -> None:
        received.append(donation)

    with caplog.at_level(logging.WARNING):
        await _handle_text("{not json", sink)
    assert received == []
    assert "could not parse websocket frame" in caplog.text


class FakeResponse:
    """Duck-typed aiohttp response returning a canned payload."""

    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def json(self) -> dict:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientError(f"HTTP {self.status}")


class FakeWS:
    """Duck-typed websocket: canned receive responses then a drain sequence."""

    def __init__(
        self,
        responses: list[dict],
        drain: list[aiohttp.WSMessage],
    ) -> None:
        self._responses = list(responses)
        self._drain = list(drain)
        self.sent: list = []

    async def __aenter__(self) -> "FakeWS":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def send_json(self, frame) -> None:
        self.sent.append(frame)

    async def receive_json(self) -> dict:
        return self._responses.pop(0)

    def __aiter__(self) -> "FakeWS":
        return self

    async def __anext__(self) -> aiohttp.WSMessage:
        if not self._drain:
            raise StopAsyncIteration
        return self._drain.pop(0)


class FakeWsContext:
    """Async context manager yielding a FakeWS."""

    def __init__(self, ws: FakeWS) -> None:
        self.ws = ws

    async def __aenter__(self) -> FakeWS:
        return self.ws

    async def __aexit__(self, *exc) -> bool:
        return False


class FakeSession:
    """Duck-typed aiohttp session returning canned HTTP/WS responses."""

    def __init__(
        self,
        token_payload: dict,
        subscribe_payload: dict,
        ws: FakeWS,
    ) -> None:
        self.token_payload = token_payload
        self.subscribe_payload = subscribe_payload
        self.ws = ws
        self.gets = 0
        self.posts = 0
        self.ws_connects = 0
        self.closed = False

    def get(self, url, headers=None) -> FakeResponse:
        self.gets += 1
        return FakeResponse(self.token_payload)

    def post(self, url, json=None, headers=None) -> FakeResponse:
        self.posts += 1
        return FakeResponse(self.subscribe_payload)

    def ws_connect(self, url, heartbeat=None) -> FakeWsContext:
        self.ws_connects += 1
        return FakeWsContext(self.ws)

    async def close(self) -> None:
        self.closed = True


def _make_settings() -> Settings:
    return Settings(
        client_id="42",
        access_token="secret",
        amqp_dsn="amqp://localhost:5672",
    )


def _text_message(data: str) -> aiohttp.WSMessage:
    return aiohttp.WSMessage(type=aiohttp.WSMsgType.TEXT, data=data, extra=None)


def _full_flow_session() -> FakeSession:
    token = {"data": {"socket_connection_token": "conn-tok"}}
    subscribe = {"channels": [{"token": "sub-tok"}]}
    ws = FakeWS(
        responses=[
            {"result": {"client": "client-uid"}},
            {"result": {"type": 1, "channel": "$alerts:donation_42"}},
        ],
        drain=[_text_message(_donation_frame())],
    )
    return FakeSession(token, subscribe, ws)


async def test_run_stream_full_flow_delivers_donation() -> None:
    session = _full_flow_session()
    gateway = AiohttpGateway(session=session)
    received: list[Donation] = []

    async def sink(donation: Donation) -> None:
        received.append(donation)

    await gateway.connect()
    outcome = await gateway.run_stream(_make_settings(), sink)

    assert outcome.connected is True
    assert received == [
        Donation(
            id=1,
            amount=12.5,
            currency="RUB",
            username="alice",
            message="hi",
            created_at="2026-08-29T10:00:00Z",
        )
    ]
    assert session.gets == 1
    assert session.posts == 1
    assert session.ws_connects == 1
    assert len(session.ws.sent) == 2


async def test_run_stream_reports_failure_on_http_error() -> None:
    class FailingGetSession(FakeSession):
        def get(self, url, headers=None) -> FakeResponse:
            return FakeResponse({}, status=500)

    session = FailingGetSession({}, {}, FakeWS([], []))
    gateway = AiohttpGateway(session=session)
    received: list[Donation] = []

    async def sink(donation: Donation) -> None:
        received.append(donation)

    outcome = await gateway.run_stream(_make_settings(), sink)

    assert outcome.connected is False
    assert received == []


async def test_connect_does_not_create_session_when_injected(monkeypatch) -> None:
    session = FakeSession({}, {}, FakeWS([], []))
    gateway = AiohttpGateway(session=session)

    def boom(*args, **kwargs) -> None:
        raise AssertionError("must not construct a real session")

    monkeypatch.setattr(aiohttp, "ClientSession", boom)

    await gateway.connect()

    assert gateway._session is session
