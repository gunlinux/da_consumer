import pytest

from redonats.domain.errors import ConfigError
from redonats.domain.models import API_BASE, HEARTBEAT_PATH, WS_URL
from redonats.infrastructure.config import load_settings

CREDS = {"DA_USER_ID": "42", "DA_ACCESS_TOKEN": "secret"}


def test_load_settings_requires_credentials() -> None:
    with pytest.raises(ConfigError, match="DA_USER_ID and DA_ACCESS_TOKEN"):
        load_settings({})


def test_load_settings_requires_amqp_dsn() -> None:
    with pytest.raises(ConfigError, match="AMQP_DSN"):
        load_settings(CREDS)


def test_load_settings_defaults() -> None:
    settings = load_settings({**CREDS, "AMQP_DSN": "amqp://localhost:5672"})
    assert settings.client_id == "42"
    assert settings.access_token == "secret"
    assert settings.api_base == API_BASE
    assert settings.ws_url == WS_URL
    assert settings.log_level == "INFO"
    assert settings.reconnect_max_delay == 30.0
    assert settings.heartbeat_path == HEARTBEAT_PATH
    assert settings.amqp_queue == "donations"
    assert settings.amqp_reconnect_delay == 5.0


def test_load_settings_overrides() -> None:
    env = {
        **CREDS,
        "AMQP_DSN": "amqp://user:pass@localhost:5672/vhost",
        "DA_LOG_LEVEL": "DEBUG",
        "DA_API_BASE": "https://api.example.test",
        "DA_WS_URL": "wss://ws.example.test/socket",
        "DA_RECONNECT_MAX_DELAY": "5.5",
        "DA_HEARTBEAT_PATH": "/tmp/hb",
        "AMQP_QUEUE": "donation_events",
        "AMQP_RECONNECT_DELAY": "7.5",
    }
    settings = load_settings(env)
    assert settings.amqp_dsn == "amqp://user:pass@localhost:5672/vhost"
    assert settings.amqp_queue == "donation_events"
    assert settings.amqp_reconnect_delay == 7.5
    assert settings.log_level == "DEBUG"
    assert settings.api_base == "https://api.example.test"
    assert settings.ws_url == "wss://ws.example.test/socket"
    assert settings.reconnect_max_delay == 5.5
    assert settings.heartbeat_path == "/tmp/hb"


def test_load_settings_rejects_bad_max_delay() -> None:
    env = {
        **CREDS,
        "AMQP_DSN": "amqp://localhost:5672",
        "DA_RECONNECT_MAX_DELAY": "soon",
    }
    with pytest.raises(ConfigError, match="DA_RECONNECT_MAX_DELAY"):
        load_settings(env)


def test_load_settings_rejects_bad_amqp_reconnect_delay() -> None:
    env = {**CREDS, "AMQP_DSN": "amqp://localhost:5672", "AMQP_RECONNECT_DELAY": "soon"}
    with pytest.raises(ConfigError, match="AMQP_RECONNECT_DELAY"):
        load_settings(env)
