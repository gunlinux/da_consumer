## 1. Publisher reliability (R1, R2, H2, H3, H4)

- [x] 1.1 Add `persist=True` to the publish call in `publish_donation`; update `test_publisher.py`'s `FakeBroker` to record kwargs and assert `persist is True` in the publish test; verify `uv run pytest tests/test_publisher.py` passes
- [x] 1.2 Add a bounded retry (3 attempts, ~0.2s/0.5s delays) around the publish inside `make_push_handler`, incrementing the shared failure counter on final failure and resetting it on success; verify a new `test_make_push_handler_retries_then_records_failure` test passes and the existing swallow-on-failure test still passes
- [x] 1.3 Change `Donation.amount` and `DonationCreate.amount` to `Decimal`, convert the DA string in `parse_donation`, and add a pydantic field serializer rendering `amount` as a JSON number; verify `test_publish_donation_publishes_json_payload_to_queue` still asserts the numeric payload `"amount": 12.5` (not a string)
- [x] 1.4 Rewrite `test_make_broker_uses_settings` to monkeypatch `RabbitBroker` in the publisher module and capture constructor kwargs (url, reconnect interval) instead of poking `_connection_kwargs`; verify the test passes
- [x] 1.5 Wrap `ensure_queue` in `_async_main` with the clean-error pattern (print `could not declare queue: …`, exit 1) — requires the staged `testable-composition-root` CLI change merged first; verify a queue-declare-failure test in `tests/test_cli.py` (or equivalent) asserts exit 1

## 2. Reconnect-loop robustness (R3, R4, T2)

- [x] 2.1 Add `MIN_STREAM_DURATION = 30.0` to `service.py` and reset `attempt` only when `outcome.connected and outcome.duration >= MIN_STREAM_DURATION`; verify new `test_service.py` tests cover both the short-connected (backoff keeps growing) and sustained (backoff resets) scenarios
- [x] 2.2 Move `gateway.connect()` inside the `try` in `run()` and create the heartbeat task only after connect succeeds; verify a test where `connect()` raises asserts the heartbeat is cancelled, `gateway.close()` is called, and no orphaned task remains
- [x] 2.3 Add a test for the `except Exception` fallback in `run()`: a gateway whose `run_stream` raises → logged, treated as disconnected, loop continues; verify it passes
- [x] 2.4 Add a direct test for `_heartbeat_loop`: writes the heartbeat file on cadence and is cancellable; verify it passes

## 3. Observability (O1, O2)

- [x] 3.1 Add the mutable `Stats` dataclass (`donations`, `publish_failures`, `last_donation_at`) with a docstring noting the deliberate exception to the frozen-dataclass convention; verify it imports and is fully typed
- [x] 3.2 Render the donation message in `log_donation` via `json.dumps(message, ensure_ascii=False)`; verify a test with spaces/quotes in the message asserts the log line still parses as key=value
- [x] 3.3 Change `write_heartbeat`/`_heartbeat_loop` to write JSON (`ts`, `donations`, `publish_failures`, `last_donation_at`) while preserving mtime semantics; wire `Stats` from `_async_main` into `run(..., stats=...)` and `make_push_handler(..., stats=...)` with a `None` default; verify heartbeat tests assert the JSON content and `tests/test_cli.py` still passes
- [x] 3.4 Log a periodic summary (every 60th heartbeat tick ≈ 15 min) with donation and publish-failure counts; verify a caplog test asserts the summary line

## 4. Gateway testability (T1)

- [x] 4.1 Add the `AiohttpGateway(session=None)` seam so `connect()` only builds a real session when none is injected; verify existing gateway tests still pass
- [x] 4.2 Add duck-typed `FakeSession`/`FakeWS` fixtures and tests for: successful full flow (token exchange → handshake → subscribe → drain, donation delivered, `StreamOutcome(connected=True)`), token-exchange HTTP failure (`connected=False`, no raise), and no real session created when one is injected; verify `uv run pytest tests/test_gateway.py` passes

## 5. Ops & deployment (R5, S1, D1, D2, D3)

- [x] 5.1 Add `deploy/redonats-health.sh` (restarts only when `docker inspect` reports `unhealthy`), `deploy/redonats-health.service`, and `deploy/redonats-health.timer` (`OnBootSec=2min`, `OnUnitActiveSec=2min`); verify `bash -n deploy/redonats-health.sh` passes
- [x] 5.2 Update `.github/deploy.sh` to install the health units, enable the timer, and `chmod 600 .env`; verify `bash -n` passes and the script remains idempotent
- [x] 5.3 Pin the `uv` image tag and the `python:3.12` base image patch in the `Dockerfile`; verify the image builds (or a `uv sync --locked` sanity check if Docker is unavailable)
- [x] 5.4 Switch `code-quality.yaml` from `uvx ruff …` to `uv run ruff …` (locked) and rename the `formating` job to `formatting`; verify the workflow YAML parses
- [x] 5.5 Add `concurrency: { group: deploy, cancel-in-progress: false }` to `deploy.yml`; verify the workflow YAML parses

## 6. Hygiene & docs (H1, H5)

- [x] 6.1 Delete `domain/formatting.py` and `tests/test_formatting.py`; verify `uv run ruff check .` and `uv run pytest` pass with no dangling imports
- [x] 6.2 Correct the README Healthcheck section (watchdog timer, not `Restart=on-failure`), state `created_at` is ISO-8601 UTC in the queue contract, and document the heartbeat JSON format; verify the README renders

## 7. Verification

- [x] 7.1 Run `uv run pytest`, `uv run ruff check .`, and `uv run ruff format --check .`; verify the full suite passes and the lint gate is clean
- [x] 7.2 Run `openspec validate --change production-readiness --strict`; verify the change validates
