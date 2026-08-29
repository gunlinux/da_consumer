# AGENTS.md

Instructional context for agents working in this repository.

## Project Overview

`redonats` is a Python 3.12 async service that listens to DonationAlerts
donations over the Centrifugo WebSocket gateway and publishes each donation
as JSON to the durable RabbitMQ `donations` queue via FastStream, mirroring
the `youtube_consumer` → RabbitMQ → downstream pipeline pattern.

Data flow:

```
[DonationAlerts]
    │
    ▼
AiohttpGateway  (aiohttp WebSocket → Centrifugo, raw protocol, no centrifuge lib)
    │  Donation (frozen dataclass)
    ▼
application/service.py  (reconnect loop, backoff, shutdown, heartbeat)
    │  PushHandler (async sink: log + publish)
    ▼
publisher.publish_donation  →  DonationCreate JSON
    ▼
RabbitMQ "donations" queue  (durable, declared on startup)
```

## Core Principles (kept from the original prompt)

- **Functional where practical** — pure, deterministic, side-effect-free
  functions; immutable data (`@dataclass(frozen=True, slots=True)`).
- **Separate pure logic from side effects** — the domain layer must never
  touch I/O (network, filesystem, env, logging, time). I/O lives at the
  boundaries: infrastructure adapters, the application publisher, the CLI.
- **Layered, dependency-inverted architecture** — CLI composition root →
  application (service, gateway protocol, publisher) → infrastructure
  adapters → domain. Domain never imports infrastructure.
- **Dependency injection over monkey-patching** — the reconnect loop depends
  on the `Gateway` protocol; tests inject fakes.
- **Fail fast, never silently ignore exceptions** — domain-specific errors
  (`ConfigError`, `ProtocolError`), meaningful messages. The one deliberate
  exception: publish failures inside `make_push_handler` are logged and
  swallowed so a broker hiccup cannot tear down the donation stream.
- **Minimize dependencies, modern typing** (3.12): `list[str]`, `X | None`,
  `Protocol`, `Final`.

## Key Components

- `src/redonats/cli.py` — composition root. `main()`: `load_dotenv`,
  `load_settings` (ConfigError → exit 2), `configure_logging`, then
  `_async_main`: `make_broker` → `broker.start()` (failure → exit 1) →
  `ensure_queue` → SIGTERM/SIGINT handlers → `run(...)` with the
  log+publish sink → `broker.stop()`.
- `src/redonats/application/service.py` — `run(settings, gateway, shutdown,
  on_push, backoff)` loop: reconnect with exponential backoff
  (`backoff_delay`, 1s base, capped by `reconnect_max_delay`), resets the
  attempt counter on a successful connection, heartbeat task writes the
  heartbeat file every 15s, clean shutdown on `shutdown` event.
- `src/redonats/application/gateway.py` — `Gateway` protocol
  (`connect/close/run_stream → StreamOutcome`) + `PushHandler`
  (`Callable[[Donation], Awaitable[None]]`) — the DI seam for tests.
- `src/redonats/application/publisher.py` — FastStream `RabbitBroker`
  factory (`make_broker`), `ensure_queue` (durable queue),
  `to_donation_create` (pure mapping), `publish_donation`,
  `make_push_handler` (log + publish, swallows publish errors).
- `src/redonats/infrastructure/gateway.py` — `AiohttpGateway`: HTTP token
  exchange (`/user/oauth`), WS handshake, `/centrifuge/subscribe`,
  subscribe frame, drain. 30s HTTP timeout, 60s WS heartbeat. Expected
  failures become `StreamOutcome(connected=False)`; unexpected errors
  propagate. `_handle_text` classifies frames: `result` frames (subscribe
  confirmations) are ignored, `push` frames are parsed.
- `src/redonats/infrastructure/config.py` — `load_settings(env)`: requires
  `DA_USER_ID`, `DA_ACCESS_TOKEN`, `AMQP_DSN`; optional `DA_LOG_LEVEL`,
  `DA_API_BASE`, `DA_WS_URL`, `DA_RECONNECT_MAX_DELAY`, `DA_HEARTBEAT_PATH`,
  `AMQP_QUEUE`, `AMQP_RECONNECT_DELAY`.
- `src/redonats/infrastructure/heartbeat.py` — `write_heartbeat(path)`,
  epoch seconds, OSError logged not raised.
- `src/redonats/infrastructure/logging_setup.py` — stdlib logging,
  `%(asctime)s %(levelname)s %(name)s %(message)s`, key=value messages.
- `src/redonats/domain/` — PURE. `models.py` (frozen `Settings`, `Donation`;
  `API_BASE`/`WS_URL`/`HEARTBEAT_PATH` constants), `protocol.py` (frame
  builders, `require_success`, token extraction, `parse_push`,
  `parse_donation`, `is_push_frame`), `formatting.py` (`format_donation`),
  `errors.py` (`ConfigError`, `ProtocolError`).

## Building and Running

Managed with `uv` (Python 3.12; see `.python-version`).

```bash
uv sync
cp env.example .env   # fill in DA_USER_ID, DA_ACCESS_TOKEN, AMQP_DSN
uv run redonats       # or: uv run python -m redonats
```

RabbitMQ is required (`AMQP_DSN`); without it the process exits 1 with a
clear message. Exit via Ctrl+C / SIGTERM.

Docker:

```bash
docker build -t redonats .
docker run --env-file .env --restart unless-stopped --detach redonats
```

## Testing

```bash
uv run pytest       # tests are in tests/, pytest-asyncio asyncio_mode=auto
uv run ruff check .
uv run ruff format --check .
```

Conventions (tests never touch the network or RabbitMQ):

- Domain parsing/formatting is tested directly against hand-built dicts
  (`tests/test_protocol.py`, `test_formatting.py`).
- The service loop uses a duck-typed `FakeGateway` replaying
  `StreamOutcome`s; backoff is injected (`fast_backoff`) so tests are
  deterministic (`tests/test_service.py`).
- The publisher uses a duck-typed `FakeBroker` recording `publish` /
  `declare_queue` calls (`tests/test_publisher.py`), mirroring
  youtube_consumer's test style.
- Async sinks in tests are `async def` closures, never plain list.append.

## Development Conventions

- New features are developed on a dedicated branch (e.g. `feature/<name>`)
  and merged via PR; never commit feature work directly to `main`. Fixes
  and deploy config changes may go straight to `main`.
- 88-column limit (ruff, `[tool.ruff] line-length = 88`, `target-version =
  py312`); ruff check + format are the lint gate.
- Full type annotations; modern typing only (`list[str]`, `X | None`).
- Module docstrings on the main modules; public functions have
  purpose/params/returns docstrings; comments explain why, not what.
- Private helpers are underscore-prefixed (`_handle_text`, `_log_only`,
  `_heartbeat_loop`).
- New code follows the layering rules: pure logic in `domain/`,
  orchestration in `application/`, I/O in `infrastructure/`, wiring in
  `cli.py`. Don't leak aiohttp/faststream types into `domain/`.
- `Settings` is a frozen dataclass — extend it and `load_settings` in
  lockstep; every env var gets an `env.example` entry.
- The `PushHandler` is async and receives `Donation`, not raw frames;
  keep protocol parsing in `domain/protocol.py`.

## Queue Contract

Published payload (DonationCreate JSON on `AMQP_QUEUE`, default
`donations`):

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

The durable queue is declared on startup (`ensure_queue`) so the producer
never publishes into a missing queue.

## CI and Deployment

- `.github/workflows/code-quality.yaml` (`ci`, on push): `uv lock --locked`,
  `uvx ruff check .`, `uvx ruff format --check .`, `uv run pytest`.
- `.github/workflows/deploy.yml` (on `ci` success on main): build and push
  `gunlinuxloki/redonats:<sha7>` + `:latest` to Docker Hub, then SSH to
  `loki@gunlinux.ru` running `.github/deploy.sh` with `DEPLOY_TAG`.
- `.github/deploy.sh` + `deploy/redonats.service`: pulls the commit, bakes
  the tag into the systemd unit (`@IMAGE_TAG@`), enables/restarts the
  service. Repo dir on the server: `/home/loki/projects/bot/da_consumer`.
- GitHub Actions secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`,
  `PRIVATE_KEY_SSH`.

## Gotchas

- The DonationAlerts token flow is **confirmed working against the live
  gateway**: `GET /api/v1/user/oauth` → `data.socket_connection_token`,
  then `POST /api/v1/centrifuge/subscribe` → `channels[0].token`, channel
  `$alerts:donation_{client_id}`. Do NOT switch to the `/centrifuge/token`
  endpoint suggested by official docs — it was validated and is wrong for
  this integration.
- The gateway pushes a subscribe-confirmation `result` frame onto the
  channel after subscribing; `is_push_frame` filters it. Don't treat it as
  a parse error.
- The heartbeat file (`DA_HEARTBEAT_PATH`, default
  `/tmp/redonats.heartbeat`) is written while the event loop is alive and
  drives the Docker HEALTHCHECK (`stat -c %Y`, 90s window). If the path is
  overridden, the Dockerfile HEALTHCHECK must be updated to match.
- Publish failures are intentionally swallowed (logged) inside
  `make_push_handler`; do not "fix" them into stream-tearing exceptions.
- Signals: SIGTERM/SIGINT map onto an `asyncio.Event` via
  `loop.add_signal_handler` (Unix-only; fine for the Linux Docker target).
  Killing a `uv run` wrapper does not deliver the signal to the child —
  signal the actual process (PID 1 in Docker is the `redonats` script).
- `broker.start()` uses faststream's `fail_fast` for the initial connect:
  an unreachable RabbitMQ exits 1 immediately (by design).
