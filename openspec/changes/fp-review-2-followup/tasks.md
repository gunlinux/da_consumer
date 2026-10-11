## 1. Narrow `run()`'s gateway-error tolerance (P1)

- [x] 1.1 Confirm `_GATEWAY_TRANSIENT_ERRORS = (OSError, RuntimeError)` is defined in `src/redonats/application/service.py` and `run()` catches it instead of `except Exception` (already present in the working tree); verify `uv run pytest tests/test_service.py` passes
- [x] 1.2 Add a `ProgrammingErrorGateway` double (or equivalent) whose `run_stream` raises a non-transient error (e.g. `TypeError`) and a test asserting `run()` propagates it (via `pytest.raises(TypeError)`) rather than reconnecting; verify the new test passes and the existing `test_unexpected_gateway_error_continues_loop` still passes for the transient (`RuntimeError`) path

## 2. Narrow `_publish_with_retry()` retry scope (P2)

- [x] 2.1 Confirm `_PUBLISH_TRANSIENT_ERRORS = (AMQPError, OSError, RuntimeError)` and the `from aio_pika.exceptions import AMQPError` import exist in `src/redonats/application/publisher.py` and `_publish_with_retry` catches it instead of `except Exception` (already present in the working tree); verify `uv run pytest tests/test_publisher.py` passes
- [x] 2.2 Add a test that a non-transient `publish` error (e.g. a `FakeBroker` whose `publish` raises `ValueError`) is attempted exactly once and propagates out of `_publish_with_retry` (no retry); verify the new test passes and the existing retry tests (`RuntimeError`) still retry

## 3. Narrow `publish_donation` to `queue: str` (P3)

- [x] 3.1 Change `publish_donation` to `publish_donation(broker: Broker, donation: Donation, queue: str)` and use `queue` in `broker.publish`; update `_publish_with_retry` to pass `settings.amqp_queue`; verify `uv run pytest tests/test_publisher.py` passes
- [x] 3.2 Update `test_publish_donation_publishes_persistent_json_payload` to call `publish_donation(broker, make_donation(), settings.amqp_queue)` (or a literal `"donations"`); verify it passes

## 4. Remove `_log_only` (P4)

- [x] 4.1 Make `log_donation` `async def` in `src/redonats/application/service.py`, delete `_log_only`, set `run()`'s default to `on_push: PushHandler = log_donation`, and change the push handler in `src/redonats/application/publisher.py` to `await log_donation(donation)`; verify both modules import (`uv run python -c "import redonats.cli"`)
- [x] 4.2 Make `test_log_donation_quotes_message` async and `await log_donation(donation)`; verify `uv run pytest tests/test_service.py tests/test_publisher.py` passes

## 5. `_async_main` returns an exit code (P5)

- [x] 5.1 Change `_async_main` in `src/redonats/cli.py` to return `int` (`0` on a clean run, `1` on broker-start or queue-declare failure) instead of `raise SystemExit(1)`, and change `run_cli` to `code = asyncio.run(_async_main(...))` then `if code: raise SystemExit(code)`; verify `uv run ruff check src/redonats/cli.py` passes
- [x] 5.2 Update `test_async_main_exits_1_on_broker_failure` and `test_async_main_exits_1_on_queue_declare_failure` to assert the return value is `1` (drop `pytest.raises(SystemExit)`), and `test_async_main_runs_stream_until_shutdown` to assert `0`; verify `uv run pytest tests/test_cli.py` passes
- [x] 5.3 Add a `run_cli` test that a non-zero `_async_main` code becomes `SystemExit(1)` (monkeypatch `redonats.cli._async_main` to an async stub returning `1`), preserving the observable exit-code contract; verify it passes

## 6. Full verification

- [x] 6.1 Run `uv run pytest` and verify the full suite passes
- [x] 6.2 Run `uv run ruff check .` and `uv run ruff format --check .` and verify the lint gate passes
- [x] 6.3 Run `openspec validate fp-review-2-followup --strict` and verify the change validates
