## Why

`src/redonats/cli.py` is the composition root, but it cannot be unit-tested: `main()` hardwires `load_dotenv`, `os.environ`, and constructs `AiohttpGateway()` itself, while `_async_main` builds a real `RabbitBroker` internally, registers real SIGTERM/SIGINT handlers via `loop.add_signal_handler`, and exits through `SystemExit`. There is no way to inject fakes, so the exit-code contract (2 on config error, 1 on RabbitMQ connect failure) and the shutdown path are only ever exercised against live infrastructure.

## What Changes

- Refactor `src/redonats/cli.py` so the composition root is dependency-injected:
  - `main()` stays the thin entry point (load `.env`, load settings, configure logging) but delegates to a testable async runner.
  - The async runner accepts the `Settings` (already injected) plus injectable seams: a broker **factory** (defaults to `make_broker`), the `Gateway` (already a parameter), and an optional sequence of signals to install handlers for (tests pass `()` so no real signal handlers are registered).
  - Exit codes are preserved and become unit-testable: `SystemExit(2)` on `ConfigError`, `SystemExit(1)` on broker start failure.
- Add `tests/test_cli.py` covering, with fakes only (no network, no RabbitMQ, no real signal registration):
  - exit code 2 when settings are invalid,
  - exit code 1 when broker start fails,
  - happy path: broker started, queue ensured, gateway stream runs, shutdown event stops the loop, broker stopped,
  - broker stop still runs when `run(...)` raises.
- Public CLI behavior (`uv run redonats`) is unchanged; this is not a breaking change.

## Capabilities

### New Capabilities

- `cli`: the composition root contract — startup sequence, exit codes (`2` config error, `1` broker connect failure), signal-driven shutdown, and injectable seams (broker factory, gateway, signal list) that make the wiring unit-testable without live infrastructure.

### Modified Capabilities

- None. No existing `openspec/specs/*` capability changes; the CLI's externally observable behavior is preserved.

## Impact

- `src/redonats/cli.py` — restructured: `main()` slimmed down, `_async_main` gains injectable seams (broker factory, optional signal sequence).
- `tests/test_cli.py` — new, following the existing fake-broker test style from `tests/test_publisher.py`; reuses the duck-typed `FakeBroker` pattern.
- No dependency changes (`pyproject.toml` untouched), no changes to `domain/`, `application/publisher.py`, `application/service.py`, or `infrastructure/`.
- `deploy/redonats.service` and `Dockerfile` unaffected.
