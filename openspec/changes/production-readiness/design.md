## Context

See proposal.md — Why. The review's fixes span four source modules (`publisher.py`, `service.py`, `infrastructure/gateway.py`, `infrastructure/heartbeat.py`), the CLI, tests, and ops files (`Dockerfile`, `.github/workflows/*`, `.github/deploy.sh`, `deploy/`, `README.md`). Current constraints that shape the design:

- The staged `testable-composition-root` change already introduces the `Broker` protocol and injectable `_async_main` seams; this change builds on it (`stats` creation and the queue-declare error handling live in `_async_main`).
- The Docker HEALTHCHECK reads the heartbeat file's **mtime** (`stat -c %Y`, 90s window) — heartbeat content can change, mtime semantics must not.
- The queue contract (JSON shape, `amount` as a JSON number) is consumed by a downstream bot; it must not change.
- Pydantic v2 serializes `Decimal` as a **string** in JSON mode (verified against the project's pydantic) — wire-compatible Decimal needs a custom serializer.
- CI has no type-checker; ruff (88 cols, py312) + pytest are the gate.

## Goals / Non-Goals

**Goals:**

- Every high/medium review finding (R1–R5, O1–O2, T1–T2) fixed with tests, preserving the existing queue contract and heartbeat-mtime healthcheck.
- Low findings (S1, D1–D3, H1–H5) addressed with minimal, reversible changes.
- Keep the fail-fast / fail-soft split: publish failures still never tear down the stream.

**Non-Goals:**

- No spool-file/dead-letter delivery path (retry + surfacing chosen instead — see D2).
- No alerting integrations (email/Telegram/Prometheus) — the repo has no alert channel; the counter + ERROR log + heartbeat data are the alert surface.
- No DA-side replay or HA (unavoidable for this integration).
- No re-litigating the CLI composition-root work already staged in `testable-composition-root`.

## Decisions

### D1. Persistent publishes (R1)

`publish_donation` passes `persist=True` to `broker.publish` (FastStream maps it to AMQP delivery-mode 2). `test_publisher.py`'s `FakeBroker` records the kwargs; the existing publish test asserts `persist is True`.

**Alternatives:** none — this is the one-line fix the review calls for. Trade-off: persistent messages cost a broker fsync/ack per message; negligible at donation volume.

### D2. Bounded retry + failure surfacing instead of spool (R2)

`make_push_handler`'s inner handler retries the publish up to 3 attempts total (delays ~0.2s, 0.5s) before giving up. On final failure it increments a `publish_failures` counter (see D3) and logs `ERROR`; on success the counter resets to 0. The donation stays in the logs (existing behavior) and the stream stays up.

**Alternatives:** a spool-file fallback drained on next successful publish — rejected: it adds a second delivery path, a drain mechanism, and crash-recovery semantics (replaying stale spools after long outages could double-deliver); the retry + surfacing covers the review's "at least one of" with far less surface. A Prometheus counter — rejected: no metrics infra in this repo.

### D3. Shared `Stats` object for counters (O1/O2)

A small mutable `Stats` dataclass (`donations`, `publish_failures`, `last_donation_at`) is created in `_async_main` (composition root) and injected into both `make_push_handler(..., stats=...)` and `run(..., stats=...)`. The heartbeat loop writes it as JSON: `{"ts": <epoch>, "donations": N, "publish_failures": M, "last_donation_at": <epoch|null>}`, preserving the mtime-based HEALTHCHECK. `_heartbeat_loop` additionally logs a periodic summary every 60th tick (15s × 60 = 15 min). `stats=None` keeps the existing `run()` signature compatible for tests that don't care.

**Alternatives:** the handler publishing counters via a callback — rejected, a shared mutable object is the project's simplest DI-friendly shape. Immutable snapshots swapped by reference — over-engineered for two counters. Note: `Stats` is a deliberate exception to the frozen-dataclass convention; document that in its docstring.

### D4. Backoff reset requires a sustained stream (R3)

`MIN_STREAM_DURATION: float = 30.0` constant in `service.py` (beside `BACKOFF_BASE`). The attempt counter resets only when `outcome.connected and outcome.duration >= MIN_STREAM_DURATION`; short "connected" streams (server kicks, LB cycling) keep the backoff growing.

**Alternatives:** an env var (`DA_MIN_STREAM_DURATION`) — rejected, adds config surface for a tuning knob that the review only suggested as a constant. Resetting on donations-received instead of duration — rejected, `duration` is already recorded and untested.

### D5. Connect failures tear down cleanly (R4)

In `run()`: `gateway.connect()` moves inside the `try`, and the heartbeat task is created **after** connect succeeds. The existing `finally` then cancels the heartbeat and calls `gateway.close()` on every exit path, including connect failure. `AiohttpGateway.close()` already tolerates a `None` session, so the double-close concern does not arise.

**Alternatives:** creating the heartbeat first and cancelling it in an `except` around connect — messier; the single `try/finally` is the project's established cleanup shape.

### D6. Watchdog = systemd timer, not `WatchdogSec` (R5)

New committed files `deploy/redonats-health.sh` (checks `docker inspect --format '{{.State.Health.Status}}' redonats`; if `unhealthy`, logs and runs `systemctl restart redonats`), `deploy/redonats-health.service`, and `deploy/redonats-health.timer` (`OnBootSec=2min`, `OnUnitActiveSec=2min`). `deploy.sh` installs the units and enables the timer (idempotent). README's Healthcheck section is corrected to describe the timer.

**Alternatives:** `WatchdogSec` + `sd_notify` from the app — rejected: requires an aiohttp/event-loop integration and a new dependency, and the heartbeat already proves loop liveness; the timer reuses the existing Docker HEALTHCHECK as its signal. A `Restart=always` + `--restart` change — rejected: still only reacts to process exit.

### D7. Quoted log values (O1)

`log_donation` renders the message with `json.dumps(message, ensure_ascii=False)` so spaces and quotes cannot break the `key=value` line. Other fields are already parser-safe (numeric/id/ISO timestamps).

**Alternatives:** `%r` (single quotes) — breaks on messages containing quotes; rejected.

### D8. `format_donation` deleted (H1)

`domain/formatting.py` and `test_formatting.py` are removed. `log_donation` keeps its structured line (with D7 quoting); `format_donation`'s human rendering duplicates it without a caller.

**Alternatives:** using `format_donation` inside `log_donation` — rejected: the structured key=value line and the human rendering have different shapes; keeping both would double-format.

### D9. `Decimal` money with a wire-compatible serializer (H2)

`Donation.amount` (domain) and `DonationCreate.amount` become `Decimal`; `parse_donation` converts the DA string to `Decimal`. Because pydantic v2 serializes `Decimal` as a string in JSON mode (verified), `DonationCreate` gains a field serializer rendering `amount` as a JSON number (float). The wire contract is unchanged — downstream still sees `"amount": 12.5` — while in-process arithmetic is decimal.

**Alternatives:** keep `float` and document the limitation — rejected (user chose full remediation, and the serializer makes the change cheap). Serialize as string — rejected, breaks the contract.

### D10. Gateway session seam (T1)

`AiohttpGateway(session: aiohttp.ClientSession | None = None)`; `connect()` only creates a real session when none was injected. Tests build a duck-typed `FakeSession` (`get`/`post` returning canned responses, `ws_connect` yielding a `FakeWS` with `send_json`/`receive_json`/`__aiter__`) and assert the full sequence — token exchange → handshake → subscribe → drain → `StreamOutcome` — plus the failure path (HTTP error → `connected=False`).

**Alternatives:** aiohttp `TestServer`/`TestClient` — rejected: the Centrifugo handshake needs a live WS handler app, far more moving parts than a double, and the project convention (AGENTS.md) is fakes over real infra.

### D11. Clean queue-declare failure (H4)

`_async_main` wraps `ensure_queue` in the same try/except shape as `broker.start()`: prints `could not declare queue: {exc}` and raises `SystemExit(1)`. Requires the staged CLI refactor (broker injection) to be merged first, since it edits the same function.

### D12. Stable broker test (H3)

`test_make_broker_uses_settings` monkeypatches `RabbitBroker` inside the `publisher` module with a recording fake and asserts the constructor received the settings' url/reconnect interval — no private-attribute poking.

**Alternatives:** finding a public attribute on `RabbitBroker` — rejected, FastStream 0.7 does not expose the url publicly.

### D13. Ops hardening (S1, D1, D2, D3)

- S1: `deploy.sh` adds `chmod 600 .env` after the quoting normalization.
- D1: Dockerfile pins `ghcr.io/astral-sh/uv:<exact>` and `python:3.12.<patch>-slim` (exact versions chosen at implementation time against the current releases; verify the image builds).
- D2: `code-quality.yaml` switches `uvx ruff …` → `uv run ruff …` (locked) and renames the `formating` job to `formatting`.
- D3: `deploy.yml` gains `concurrency: { group: deploy, cancel-in-progress: false }`.

## Risks / Trade-offs

- [Retry latency] → bounded at 3 attempts / ~0.7s worst case; the stream itself never blocks on this.
- [Persistent-message throughput cost] → one fsync-ish ack per message; donation volume is far below broker limits.
- [Heartbeat content change surprises external readers] → no known consumers besides the mtime HEALTHCHECK; README notes the JSON format.
- [Timer restart racing a deploy] → the health script only restarts on `unhealthy`; a restart during an in-flight deploy uses the already-baked unit (tag unchanged) — at worst one redundant restart, documented in deploy.sh comments.
- [`Decimal` serializer drift] → the serializer keeps the exact number shape; the publisher test asserts `"amount": 12.5` (number, not string) so a regression fails CI.
- [Queue-declare change depends on the staged CLI refactor] → tasks order the merge/rebase so the CLI change lands first; if it is not merged, `_async_main`'s error handling is rebased onto its new shape.

## Migration Plan

Feature branch + PR per AGENTS.md. Deploy impact is additive: `deploy.sh` installs two new systemd units and enables the timer on the next deploy (idempotent); the app image changes are internal. Rollback is a revert of the commit plus removing the timer units (`systemctl disable --now redonats-health.timer`); the queue contract and HEALTHCHECK semantics never change, so no ops coordination is needed beyond the deploy itself.

## Open Questions

None — the pydantic `Decimal` serialization behavior was verified up front, and the exact pinned versions (uv release, Python patch) are implementation-time constants that do not change the approach or the tasks.
