import json
import logging

from redonats.domain.models import Donation
from redonats.infrastructure.gateway import _handle_text


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
