## Why

The 2026-08-29 production-readiness review (`REV.md`) concluded the pipeline is not yet fully safe as a money stream: messages are published **non-persistent** (lost on broker restart despite the durable queue), publish failures are swallowed with no retry or alert (silent donation loss), the reconnect backoff never engages after short-lived "connected" streams, a failed `gateway.connect()` leaks the heartbeat task, and the Docker HEALTHCHECK can never trigger a restart because systemd `Restart=on-failure` only reacts to process exit. Observability, CI/CD reproducibility, and a few code-hygiene items compound the risk. None of these are architectural — the fixes are one-liners or small unit changes.

## What Changes

- **R1 — Persistent publishes**: `publish_donation` publishes with `persist=True` so queued messages survive broker restarts; the publisher test asserts the kwarg.
- **R2 — Bounded retry + failure alert**: the push handler retries a failed publish up to 3 times with small backoff, then logs `ERROR`; a publish-failure counter is surfaced in the heartbeat file (with a periodic summary log line) instead of failing silently. Spool-file fallback is consciously **not** chosen (see design).
- **R3 — Backoff engages after short streams**: the reconnect attempt counter only resets when a connected stream lasted ≥ 30s (`StreamOutcome.duration`, already recorded but unused), stopping 1s reconnect hammering on flaky links.
- **R4 — Connect-failure cleanup**: `gateway.connect()` moves inside the `try` in `run()` so the `finally` cancels the heartbeat and closes the gateway even when connect raises; regression test added.
- **R5 — Unhealthy containers actually restart**: a systemd timer (`redonats-health.timer` + unit) inspects `docker inspect` health and restarts the container when unhealthy; README's incorrect `Restart=on-failure` claim corrected.
- **O1 — Parseable logs + metrics**: donation `message` is JSON-quoted in the log line; counters (donations, publish failures) are written into the heartbeat file and a periodic summary line is logged.
- **O2 — Heartbeat carries stream activity**: heartbeat file becomes JSON (`ts`, `donations`, `publish_failures`, `last_donation_at`) while keeping the mtime semantics the Docker HEALTHCHECK relies on.
- **S1 — Credential file permissions**: `deploy.sh` enforces `chmod 600` on the server `.env`.
- **T1 — Gateway full-flow tests**: `AiohttpGateway` gains an injectable HTTP-session seam and the token-exchange → handshake → subscribe → drain sequence is covered with a fake session (no network).
- **T2 — `run()` branch coverage**: unexpected-gateway-exception fallback, connect-failure cleanup, and `_heartbeat_loop` get tests.
- **D1 — Reproducible image**: Dockerfile pins the `uv` version and the `python:3.12` base image patch.
- **D2 — Locked linting in CI**: `uvx ruff …` replaced with `uv run ruff …` (locked); the `formating` job-name typo fixed.
- **D3 — Serialized deploys**: `concurrency` group added to `deploy.yml` so overlapping pushes cannot interleave two deploys.
- **H1 — Dead code**: `format_donation` (unused) is deleted together with `test_formatting.py`.
- **H2 — Money as `Decimal`**: `Donation.amount` / `DonationCreate.amount` become `Decimal`, serialized back to a JSON **number** so the wire contract is unchanged (downstream sees `"amount": 12.5`).
- **H3 — Stable broker test**: `test_make_broker_uses_settings` stops poking the private `_connection_kwargs`; it captures constructor kwargs via a monkeypatched factory.
- **H4 — Clean queue-declare failure**: an `ensure_queue` failure at startup prints the same clean "could not connect to RabbitMQ"-style message and exits 1 instead of a raw traceback.
- **H5 — Contract doc**: README queue contract states `created_at` is ISO-8601 UTC.

**Out of scope (deliberately):** CLI composition-root testability (A2/T3) — already delivered by the staged `testable-composition-root` change (`tests/test_cli.py`, injectable broker factory). S2 (no secrets in image — verified fine), R6 (no DA replay — unavoidable), D4 (deploy mechanics — solid) need no action.

## Capabilities

### New Capabilities

- `publisher`: donation delivery reliability — persistent publishes, bounded publish retry, failure surfacing, `Decimal` money, clean queue-declare startup errors.
- `service`: reconnect-loop robustness — sustained-stream backoff reset, connect-failure cleanup, unexpected-gateway-error handling.
- `gateway`: `AiohttpGateway` full-flow testability via an injected HTTP session.
- `observability`: parseable key=value logs, counters in the heartbeat file, periodic summary line.
- `deploy`: unhealthy-container watchdog, `.env` permissions, pinned image build, locked CI linting, serialized deploys, accurate README claims.

### Modified Capabilities

- None. No existing specs under `openspec/specs/`; all five are new.

## Impact

- `src/redonats/application/publisher.py` — `persist=True`, retry loop, counters, `Decimal`, `Broker`-typed helpers.
- `src/redonats/application/service.py` — backoff reset threshold, connect-ordering fix, stats wiring, summary log.
- `src/redonats/domain/models.py` — `Donation.amount` → `Decimal`; `domain/formatting.py` deleted.
- `src/redonats/infrastructure/gateway.py` — injectable session seam.
- `src/redonats/infrastructure/heartbeat.py` — JSON heartbeat content.
- `src/redonats/cli.py` — stats creation + queue-declare error handling (only if the staged CLI change is merged first).
- `tests/` — new/updated tests for all of the above; `test_formatting.py` removed.
- `Dockerfile`, `.github/workflows/*`, `.github/deploy.sh`, `deploy/` (new health timer unit), `README.md`.
- No new runtime dependencies; `pyproject.toml` unchanged.
