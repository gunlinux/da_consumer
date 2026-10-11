## Why

`FP_REVIEW_2.md` (the second `check-fp` purity audit) confirms the layering holds — `domain/` stays 100% pure and every 🔴 finding is an intentional boundary side effect — but it flags two broad `except Exception` blocks (criterion 12) that swallow programming errors, not just the intended runtime failures: `run()` folds *every* gateway failure into a reconnect outcome, and `_publish_with_retry()` retries regardless of failure class. Three smaller 🟢/🟡 items remain: `publish_donation` takes the whole `Settings` for a single field, `_log_only` is a trivial async wrapper around `log_donation`, and `_async_main` raises `SystemExit` from inside a `try/finally`.

## What Changes

- **P1 — `run()` tolerates only transient gateway failures.** The reconnect loop narrows its `except Exception` to `_GATEWAY_TRANSIENT_ERRORS = (OSError, RuntimeError)`. Expected gateway failures (timeouts, HTTP errors, protocol errors) are already folded into `StreamOutcome` by the gateway; these two are the residual transport errors worth retrying. Programming errors (`TypeError`, `ValueError`, …) now propagate and fail fast instead of looping forever. *(spec change)*
- **P2 — `_publish_with_retry()` retries only transient broker failures.** The bounded retry narrows its `except Exception` to `_PUBLISH_TRANSIENT_ERRORS = (AMQPError, OSError, RuntimeError)`. A non-transient failure (e.g. a serialization bug) propagates instead of being retried pointlessly. *(spec change)*
- **P3 — `publish_donation` takes the queue, not the whole `Settings`.** The signature becomes `publish_donation(broker, donation, queue: str)`; callers pass `settings.amqp_queue` explicitly. *(pure refactor — no spec-level behavior change)*
- **P4 — `_log_only` is removed.** `log_donation` becomes `async` and serves directly as the default `on_push`, eliminating the one-line wrapper. The log line content is unchanged. *(pure refactor — no spec-level behavior change)*
- **P5 — `_async_main` returns an exit code instead of raising `SystemExit`.** The `print` + `raise SystemExit(1)` moves out of `_async_main`'s `try/finally`; `_async_main` returns `0`/`1` and `run_cli` converts a non-zero code to `SystemExit`. Observable exit codes (0/1/2) are unchanged. *(pure refactor — no spec-level behavior change)*

No breaking changes. The queue contract, reconnect policy, heartbeat-mtime semantics, publish-swallowing/fail-soft split, and CLI exit codes are all preserved.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `service`: "Unexpected gateway errors do not stop the listener" is narrowed to transient transport errors — a stream attempt raising a *programming* error now propagates instead of being treated as a failed reconnect attempt.
- `publisher`: "Publish failures are retried" is narrowed to transient broker/protocol failures — a *non-transient* publish failure is not retried.

P3, P4, and P5 are pure internal refactors with no externally-observable behavior change, so they are captured in `design.md` and `tasks.md` but introduce no spec delta.

## Impact

- `src/redonats/application/service.py` — `_GATEWAY_TRANSIENT_ERRORS` constant; `log_donation` becomes `async`; `_log_only` removed; `run()` default `on_push` becomes `log_donation`.
- `src/redonats/application/publisher.py` — `_PUBLISH_TRANSIENT_ERRORS` constant + `AMQPError` import; `publish_donation(broker, donation, queue: str)`; `_publish_with_retry` narrowed; the push handler `await log_donation(...)`.
- `src/redonats/cli.py` — `_async_main` returns `int`; `run_cli` raises `SystemExit` on a non-zero code.
- `tests/test_service.py`, `tests/test_publisher.py`, `tests/test_cli.py` — new/updated tests for transient-only continue/retry semantics, the async `log_donation`, the narrowed `publish_donation` signature, and the `_async_main` return code.
- No new runtime dependencies; `pyproject.toml` unchanged.
