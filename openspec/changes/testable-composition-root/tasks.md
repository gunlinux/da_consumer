## 1. Refactor the composition root

- [x] 1.1 Add a minimal `Broker` protocol (`start`, `stop`, `declare_queue`, `publish`) to `src/redonats/application/publisher.py` beside `make_broker`, and verify `make_broker`'s returned `RabbitBroker` satisfies it structurally and `uv run pytest tests/test_publisher.py` still passes
- [x] 1.2 Extract `run_cli(env: Mapping[str, str | None], gateway: Gateway) -> None` from `main()` in `src/redonats/cli.py` (holds `load_settings`/`configure_logging`/`SystemExit(2)`/`asyncio.run`), making `main()` a thin `load_dotenv()` + `run_cli(os.environ, AiohttpGateway())` wrapper, and verify `uv run ruff check src/redonats/cli.py` passes and exit code 2 is raised before `asyncio.run`
- [x] 1.3 Extend `_async_main` with keyword-only seams — `broker_factory: Callable[[Settings], Broker] = make_broker`, `signals: tuple[signal.Signals, ...] = (signal.SIGTERM, signal.SIGINT)`, `shutdown: asyncio.Event | None = None` (created internally and wired to `signals` when omitted; handlers removed in `finally`) — and verify the existing `uv run pytest tests/` suite still passes unchanged

## 2. Add composition root tests

- [x] 2.1 Add `tests/test_cli.py` with a duck-typed `FakeBroker` (records `start`/`stop`/`declare_queue` calls, reusing the `test_publisher.py` style) and a `FakeGateway`, and verify a config-error test (`run_cli` with missing `DA_USER_ID`/`AMQP_DSN`) raises `SystemExit` with code 2 and prints a configuration error message
- [x] 2.2 Add a test where `broker_factory` returns a fake whose `start()` raises, and verify `_async_main` raises `SystemExit` with code 1 and prints a RabbitMQ connection error (no real broker, `signals=()`)
- [x] 2.3 Add a happy-path test: `_async_main` with fake broker factory, fake gateway, `signals=()`, and an injected shutdown event — assert broker started once, queue declared, stream ran, handlers not registered, and broker stopped after the event is set
- [x] 2.4 Add a test where the stream raises inside `run(...)`, and verify `broker.stop()` is still awaited before the exception propagates

## 3. Verification

- [x] 3.1 Run `uv run ruff check .` and `uv run ruff format --check .` and verify both pass on the new and changed files
- [x] 3.2 Run `uv run pytest` and verify the full suite (including `tests/test_cli.py`) passes
