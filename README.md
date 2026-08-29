# redonats

DonationAlerts donation listener. Connects to the DonationAlerts
Centrifugo gateway over WebSocket, subscribes to the donation channel,
logs every donation as a structured `key=value` line and publishes it to
a durable RabbitMQ queue via FastStream.

The stream is self-healing: on disconnect it reconnects with exponential
backoff, and it shuts down cleanly on SIGTERM/SIGINT. While the event
loop is alive it keeps a heartbeat file fresh so containers can report
health.

```
[DonationAlerts]
    │
    ▼
redonats  (aiohttp WebSocket → Centrifugo gateway)
    │  publish JSON  (DonationCreate)
    ▼
RabbitMQ "donations" queue  (durable, declared on startup)
```

## Requirements

- Python 3.12 (managed with [uv](https://docs.astral.sh/uv/))
- A DonationAlerts application with credentials for your user:
  - `DA_USER_ID` — DonationAlerts user id
  - `DA_ACCESS_TOKEN` — access token for that user
- A reachable RabbitMQ broker (`AMQP_DSN`)

## Configuration

| Variable                  | Required | Default                                            | Description                                  |
| ------------------------- | -------- | -------------------------------------------------- | -------------------------------------------- |
| `DA_USER_ID`              | yes      | —                                                  | DonationAlerts user id                       |
| `DA_ACCESS_TOKEN`         | yes      | —                                                  | DonationAlerts access token                  |
| `AMQP_DSN`                | yes      | —                                                  | RabbitMQ connection string                   |
| `DA_LOG_LEVEL`            | no       | `INFO`                                             | Logging level (DEBUG, INFO, WARNING, ...)    |
| `DA_API_BASE`             | no       | `https://www.donationalerts.com/api/v1`            | Gateway REST base URL                        |
| `DA_WS_URL`               | no       | `wss://centrifugo.donationalerts.com/connection/websocket` | Centrifugo websocket URL           |
| `DA_RECONNECT_MAX_DELAY`  | no       | `30`                                               | Upper bound (seconds) for reconnect backoff  |
| `DA_HEARTBEAT_PATH`       | no       | `/tmp/redonats.heartbeat`                          | Heartbeat file for the container healthcheck |
| `AMQP_QUEUE`              | no       | `donations`                                        | RabbitMQ queue name                          |
| `AMQP_RECONNECT_DELAY`    | no       | `5.0`                                              | Broker reconnect interval (seconds)          |

## Queue contract

Every donation is published to `AMQP_QUEUE` as JSON:

```json
{
  "id": 1,
  "amount": 12.5,
  "currency": "RUB",
  "username": "alice",
  "message": "hello",
  "created_at": "2026-08-29T10:00:00Z"
}
```

The durable queue is declared on startup (`ensure_queue`), so the
producer never publishes into a missing queue. A failed publish is
logged and swallowed — the donation is still in the logs and the stream
stays up.

## Local development

```sh
uv sync
cp env.example .env   # fill in credentials (DA_USER_ID, DA_ACCESS_TOKEN, AMQP_DSN)
uv run redonats       # or: uv run python -m redonats
```

## Tests and lint

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests never touch the network or RabbitMQ: the protocol is pure, the
gateway and broker are replaced by fakes.

## CI and deployment

Push to `main` triggers the `ci` workflow (lockfile, ruff check, ruff
format, pytest). When it passes, `Deploy to Server` builds the image,
pushes `gunlinuxloki/da_consumer:<sha7>` + `:latest` to Docker Hub, and
SSHes into `loki@gunlinux.ru` to run `.github/deploy.sh`, which installs
`deploy/redonats.service` (systemd unit with the tag baked in) and
restarts the service.

Secrets required in GitHub Actions:

- `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` — Docker Hub push access
- `PRIVATE_KEY_SSH` — SSH key for `loki@gunlinux.ru`

On the server, the repo lives at `/home/loki/projects/bot/da_consumer`
with a populated `.env` (the unit passes it to the container with
`--env-file`). The deploy script normalizes `KEY="value"` quoting that
`docker --env-file` does not strip.

## Healthcheck

The image declares a `HEALTHCHECK` that verifies the heartbeat file is
newer than 90 seconds. The listener writes it every 15 seconds while the
event loop is alive, so an unhealthy state means the process is wedged
or crashed — the systemd unit (`Restart=on-failure`) brings it back.

If you override `DA_HEARTBEAT_PATH`, update the path in the Dockerfile
`HEALTHCHECK` accordingly.

## Architecture

```
cli.py (composition root)  → broker.start / ensure_queue / signal handling
  ├─ application/service.py     reconnect loop, backoff, shutdown, heartbeat
  ├─ application/gateway.py     Gateway protocol (DI seam)
  ├─ application/publisher.py   RabbitBroker factory + donation sink
  ├─ infrastructure/gateway.py  aiohttp adapter (HTTP + WebSocket)
  └─ domain/protocol.py         pure Centrifugo parsing
```

The domain layer is pure (no I/O): models, protocol parsing and
formatting, all unit-tested without network. Every side effect lives in
the infrastructure adapters, the application publisher or the CLI
composition root.
