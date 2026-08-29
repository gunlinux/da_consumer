## Context

See proposal.md — Why. The current `src/redonats/cli.py` hardwires every boundary: `main()` reads `os.environ`, constructs `AiohttpGateway()`, and `_async_main` builds the real `RabbitBroker` internally while registering real SIGTERM/SIGINT handlers. `run()` in `application/service.py` already accepts an injectable `Gateway`, `shutdown` event, `on_push` sink, and `backoff` — the untestable part is purely the composition wiring between `main()` and `run()`. Tests in `tests/test_service.py` and `tests/test_publisher.py` already demonstrate the duck-typed fake style (FakeGateway, FakeBroker) the CLI tests should mirror. CI runs ruff + pytest only (no mypy), so typing stays documentation-grade.

## Goals / Non-Goals

**Goals:**

- Make the full CLI startup/teardown sequence exercisable in unit tests with fakes: broker start, queue declaration, stream run, shutdown, broker stop.
- Make exit codes 2 (config error) and 1 (RabbitMQ unreachable) unit-testable.
- Keep `main()`'s public behavior byte-for-byte identical (same exit codes, same messages, same startup order) so `uv run redonats`, Docker HEALTHCHECK, and systemd are unaffected.

**Non-Goals:**

- No behavior changes: publish-swallowing, reconnect backoff, heartbeat timing, and the "no `broker.stop()` on broker-start failure" quirk (existing behavior, preserved deliberately) are out of scope.
- No new dependencies, no changes to `domain/`, `application/service.py`, `application/publisher.py` logic, or `infrastructure/`.

## Decisions

### 1. Extract `run_cli(env, gateway)` from `main()`

`main()` becomes a two-line wrapper: `load_dotenv()` then `run_cli(os.environ, AiohttpGateway())`. `run_cli` holds the sync orchestration — `load_settings(env)` → `configure_logging` → `SystemExit(2)` on `ConfigError` → `asyncio.run(_async_main(...))`.

**Why:** the config-error path is only reachable through `main()` today, which is pinned to `os.environ` and `load_dotenv()`. A `Mapping` parameter lets tests pass a hand-built env dict; because `run_cli` raises `SystemExit(2)` *before* `asyncio.run`, tests can call it synchronously with `pytest.raises(SystemExit)` without touching a running loop.

**Alternatives:** monkeypatching `os.environ`/`sys.argv` and calling `main()` — rejected, the project convention is DI over monkey-patching (AGENTS.md). Making `load_settings` return a sentinel — rejected, obscures the exit-code contract.

### 2. Inject a broker factory into `_async_main`

`_async_main(settings, gateway, *, broker_factory=make_broker, signals=(SIGTERM, SIGINT), shutdown=None)`. The broker is still constructed inside the runner (composition root stays the owner of construction), but through the injected factory.

**Why:** tests pass `broker_factory=lambda s: FakeBroker()`, exercising the whole start/ensure/stream/stop sequence against a duck-typed fake instead of a live RabbitMQ connection. The production path is unchanged: `broker_factory=make_broker` is the default.

**Alternatives:** injecting a pre-built broker instance — rejected: `make_broker(settings)` needs `settings` and constructing a real `RabbitBroker` in tests would pull faststream types into the test. Factory injection keeps construction at the composition root, which is its job.

### 3. Inject the signal sequence and the shutdown event

`signals` (default `(signal.SIGTERM, signal.SIGINT)`) selects which handlers `loop.add_signal_handler` installs; tests pass `()` so no OS handlers are ever registered. `shutdown` (default `None`) lets tests hand in their own `asyncio.Event` — when `None`, the runner creates one and wires it to `signals`; when provided, it is used as-is. Both handlers are removed in a `finally`, preserving the current cleanup.

**Why:** without a handle on the shutdown event a test cannot terminate the `run()` loop (it spins on successful outcomes), and without an injectable signal list a test would install real SIGTERM/SIGINT handlers inside the pytest process. This mirrors the existing `run(..., shutdown=...)` signature — the runner passes the event straight through.

**Alternatives:** driving shutdown by cancelling the runner task — rejected, cancellation is not a clean shutdown and would skip the remove-handlers/stop-broker assertions. A dedicated "signal source" abstraction — rejected as over-engineering for two signals.

### 4. Add a `Broker` protocol beside `make_broker`

Define a minimal structural `Broker` Protocol in `application/publisher.py` (`start`, `stop`, `declare_queue`, `publish`) and type `broker_factory` as `Callable[[Settings], Broker]`. FastStream's `RabbitBroker` satisfies it structurally; the duck-typed fakes in tests satisfy it by construction.

**Why:** the existing `Gateway` protocol is the project's established DI seam (AGENTS.md: "the DI seam for tests"); `Broker` extends the same pattern to the publisher side and makes the factory signature readable. Since CI has no type-checker, this is documentation-grade, but it keeps the seam explicit and greppable.

**Alternatives:** typing the factory as `Callable[[Settings], RabbitBroker]` — would force fakes to pretend to be RabbitBroker and leak faststream into the seam. Adding the protocol to `application/gateway.py` — rejected, the broker's home is `publisher.py`.

### 5. Keep the `try/finally` structure and the no-stop-on-start-failure quirk

The `broker.stop()` `finally` wraps the ensure/stream section only; a failed `broker.start()` still raises `SystemExit(1)` without calling `stop()`. This matches the spec ("Broker is stopped when the stream raises") and preserves existing behavior exactly.

**Why:** changing it would alter behavior outside the spec's contract and add no value — a failed `start()` leaves nothing to tear down.

## Risks / Trade-offs

- **Refactor drift** (exit codes, messages, startup order) → the new `tests/test_cli.py` encodes the spec scenarios; CI runs pytest on every push.
- **A test forgetting `signals=()` could register real signal handlers in the pytest process** → handler installation is conditional on the injected sequence, and tests are written to always pass `()`; the suite's fakes make accidental live wiring visible (broker never touched → no real RabbitMQ dependency).
- **`SystemExit` raised from awaited coroutines can surprise** → tests assert it via `pytest.raises(SystemExit)` and the `finally: await broker.stop()` guarantees teardown assertions still run.
- **Duck-typed fakes can drift from the `Broker` protocol** (no mypy in CI) → mitigated by the protocol's presence as documentation and by the fact that every fake method is exercised by the scenarios.

## Migration Plan

Internal refactor with no deployment impact: ship on a `feature/` branch, merge via PR per AGENTS.md conventions. Rollback is a revert of the commit; the CLI surface (`uv run redonats`, exit codes, Docker/systemd wiring) never changes, so no ops coordination is needed.

## Open Questions

None — the spec scenarios, approach, and task breakdown are fully determined by the decisions above.
