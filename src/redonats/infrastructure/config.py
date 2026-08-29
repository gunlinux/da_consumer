"""Environment-driven configuration loading (infrastructure boundary)."""

from collections.abc import Mapping

from redonats.domain.errors import ConfigError
from redonats.domain.models import API_BASE, HEARTBEAT_PATH, WS_URL, Settings


def load_settings(env: Mapping[str, str | None]) -> Settings:
    """Build Settings from an environment variable mapping.

    Args:
        env: environment mapping, e.g. ``os.environ``.

    Returns:
        Validated settings with all optional fields resolved.

    Raises:
        ConfigError: if DA_USER_ID, DA_ACCESS_TOKEN or AMQP_DSN is unset,
            or a numeric variable cannot be parsed.
    """
    client_id = env.get("DA_USER_ID")
    access_token = env.get("DA_ACCESS_TOKEN")
    amqp_dsn = env.get("AMQP_DSN")
    if not client_id or not access_token:
        raise ConfigError("DA_USER_ID and DA_ACCESS_TOKEN must be set")
    if not amqp_dsn:
        raise ConfigError("AMQP_DSN must be set")
    try:
        reconnect_max_delay = float(env.get("DA_RECONNECT_MAX_DELAY") or 30.0)
        amqp_reconnect_delay = float(env.get("AMQP_RECONNECT_DELAY") or 5.0)
    except ValueError as exc:
        raise ConfigError(
            "DA_RECONNECT_MAX_DELAY and AMQP_RECONNECT_DELAY must be numbers"
        ) from exc
    return Settings(
        client_id=client_id,
        access_token=access_token,
        api_base=env.get("DA_API_BASE") or API_BASE,
        ws_url=env.get("DA_WS_URL") or WS_URL,
        log_level=env.get("DA_LOG_LEVEL") or "INFO",
        reconnect_max_delay=reconnect_max_delay,
        heartbeat_path=env.get("DA_HEARTBEAT_PATH") or HEARTBEAT_PATH,
        amqp_dsn=amqp_dsn,
        amqp_queue=env.get("AMQP_QUEUE") or "donations",
        amqp_reconnect_delay=amqp_reconnect_delay,
    )
