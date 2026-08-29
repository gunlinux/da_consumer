import json

import pytest

from redonats.domain.errors import ProtocolError
from redonats.domain.models import Donation
from redonats.domain.protocol import (
    build_connect_frame,
    build_subscribe_frame,
    donation_channel,
    extract_connection_token,
    extract_subscription_token,
    is_push_frame,
    parse_donation,
    parse_push,
    parse_welcome,
    require_success,
)


def test_donation_channel() -> None:
    assert donation_channel("42") == "$alerts:donation_42"


def test_build_connect_frame() -> None:
    assert build_connect_frame("tok") == {"params": {"token": "tok"}, "id": 1}


def test_build_subscribe_frame() -> None:
    assert build_subscribe_frame("$alerts:donation_42", "tok") == {
        "params": {"channel": "$alerts:donation_42", "token": "tok"},
        "method": 1,
        "id": 2,
    }


def test_require_success_passes_without_error() -> None:
    require_success({"result": {"client": "abc"}})


def test_require_success_raises_on_error() -> None:
    with pytest.raises(ProtocolError, match="gateway error"):
        require_success({"error": {"code": 100, "message": "denied"}})


def test_parse_welcome_returns_client() -> None:
    assert parse_welcome({"result": {"client": "uid-1"}}) == "uid-1"


def test_parse_welcome_raises_without_result() -> None:
    with pytest.raises(ProtocolError, match="no result"):
        parse_welcome({"error": {}})


def test_parse_welcome_raises_without_client() -> None:
    with pytest.raises(ProtocolError, match="no client uid"):
        parse_welcome({"result": {}})


def test_extract_connection_token() -> None:
    payload = {"data": {"socket_connection_token": "tok-1"}}
    assert extract_connection_token(payload) == "tok-1"


def test_extract_connection_token_raises_when_missing() -> None:
    with pytest.raises(ProtocolError, match="socket_connection_token"):
        extract_connection_token({"data": {}})


def test_extract_subscription_token() -> None:
    payload = {"channels": [{"token": "tok-2"}]}
    assert extract_subscription_token(payload) == "tok-2"


def test_extract_subscription_token_raises_when_empty() -> None:
    with pytest.raises(ProtocolError, match="no channels"):
        extract_subscription_token({"channels": []})


DONATION_DATA = {
    "id": "1",
    "amount": "12.50",
    "currency": "RUB",
    "username": "alice",
    "message": "hello",
    "created_at": "2026-08-29T10:00:00Z",
}


def test_parse_donation() -> None:
    donation = parse_donation(DONATION_DATA)
    assert donation == Donation(
        id=1,
        amount=12.5,
        currency="RUB",
        username="alice",
        message="hello",
        created_at="2026-08-29T10:00:00Z",
    )


def test_parse_donation_defaults_message() -> None:
    donation = parse_donation({**DONATION_DATA, "message": None})
    assert donation.message == ""


def test_parse_donation_raises_when_field_missing() -> None:
    with pytest.raises(ProtocolError, match="misses required fields"):
        parse_donation({k: v for k, v in DONATION_DATA.items() if k != "amount"})


def test_parse_push_with_json_string_data() -> None:
    envelope = {"push": {"data": json.dumps(DONATION_DATA)}}
    assert parse_push(envelope).id == 1


def test_parse_push_with_object_data() -> None:
    envelope = {"push": {"data": DONATION_DATA}}
    assert parse_push(envelope).id == 1


def test_parse_push_raises_on_bad_json() -> None:
    with pytest.raises(ProtocolError, match="not valid JSON"):
        parse_push({"push": {"data": "{oops"}})


def test_parse_push_raises_without_push() -> None:
    with pytest.raises(ProtocolError, match="no push"):
        parse_push({})


def test_is_push_frame_accepts_pushes() -> None:
    assert is_push_frame({"push": {"data": {}}}) is True


def test_is_push_frame_rejects_command_results() -> None:
    frame = {
        "result": {
            "type": 1,
            "channel": "$alerts:donation_42",
            "data": {"info": {"user": "Client:14474"}},
        }
    }
    assert is_push_frame(frame) is False
