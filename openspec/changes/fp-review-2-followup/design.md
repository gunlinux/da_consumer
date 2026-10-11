## Context

See proposal.md — Why. The five findings all sit in already-correctly-layered code, so the changes are small and localized:

- **P1** — `run()` (`application/service.py`) catches `except Exception` around `gateway.run_stream(...)` and folds *every* failure into a reconnect outcome. The gateway already folds expected failures (`TimeoutError`, `aiohttp.ClientError`, `OSError`, `ProtocolError`) into `StreamOutcome`; the residual unexpected errors worth retrying are transport-level.
- **P2** — `_publish_with_retry()` (`application/publisher.py`) catches `except Exception` and retries regardless of failure class. `aio_pika` surfaces broker protocol failures as `AMQPError` and dropped connections as `OSError`/`RuntimeError`.
- **P3** — `publish_donation(broker, donation, settings)` uses only `settings.amqp_queue`.
- **P4** — `log_donation` (sync) is wrapped by `_log_only` (async) solely to serve as `run()`'s default `on_push`.
- **P5** — `_async_main` (`cli.py`) raises `SystemExit(1)` from inside two `try/finally` blocks.

The `service` and `publisher` base specs are introduced by the sibling `production-readiness` change; `cli` by `testable-composition-root`. None are synced to `openspec/specs/` yet. CI runs `ruff check` / `ruff format --check` / `pytest` only — no type checker, so annotations are documentation-grade.

> Note: the P1 and P2 source changes (`_GATEWAY_TRANSIENT_ERRORS`, `_PUBLISH_TRANSIENT_ERRORS`, and the `AMQPError` import) are already present in the working tree from an earlier informal pass, but they have no tests, no spec delta, and no documented change. This change formalizes them and adds P3–P5.

## Goals / Non-Goals

**Goals:**

- Narrow `run()`'s catch so programming errors fail fast instead of looping forever (P1).
- Narrow `_publish_with_retry()` so non-transient failures are not retried pointlessly (P2).
- Narrow `publish_donation` to its single real dependency, the queue name (P3).
- Remove the `_log_only` wrapper by making `log_donation` async (P4).
- Move `SystemExit(1)` out of `_async_main`'s `try/finally` so the runner returns an exit code (P5).

**Non-Goals:**

- `run()` keeps its six flat parameters — see D6; grouping them is rejected.
- The publish-swallowing/fail-soft split is untouched: `make_push_handler`'s `handler` keeps its broad `except Exception` because that is the *deliberate* boundary that prevents a broker hiccup from tearing down the stream. Only the *retry* inside `_publish_with_retry` is narrowed.
- `_publish_with_retry` and `make_push_handler` keep taking `settings`; only `publish_donation` narrows (the review flagged `publish_donation` specifically).
- No queue-contract, reconnect-policy, heartbeat-mtime, or exit-code change.

## Decisions

### D1. Narrow `run()`'s catch to transport errors (P1)

Change `except Exception` to `except _GATEWAY_TRANSIENT_ERRORS`, where `_GATEWAY_TRANSIENT_ERRORS = (OSError, RuntimeError)`. Expected gateway failures are already folded into `StreamOutcome` by `AiohttpGateway.run_stream`; the tuple is the safety net for transport errors that can still surface outside those internal catches (a closed session/loop, an event-loop teardown error). Programming errors (`TypeError`, `ValueError`, `AttributeError`, …) are not in the tuple and propagate, so a bug in `run_stream` or `on_push` fails fast instead of being retried forever.

**Alternatives:** keeping `except Exception` — rejected, that is the finding under review. Catching a single type — rejected, both `OSError` and `RuntimeError` are legitimate transport surfaces. Catching `BaseException` — rejected, would swallow `CancelledError`/`KeyboardInterrupt`.

### D2. Narrow `_publish_with_retry()` to transient broker failures (P2)

Change `except Exception` to `except _PUBLISH_TRANSIENT_ERRORS`, where `_PUBLISH_TRANSIENT_ERRORS = (AMQPError, OSError, RuntimeError)`. `AMQPError` (from `aio_pika`) covers broker protocol errors (channel closed, delivery failed); `OSError`/`RuntimeError` cover how `aio_pika` surfaces a dropped connection. A non-transient failure — e.g. a pydantic validation error from `to_donation_create` — now propagates out of `_publish_with_retry` on the first attempt instead of being retried three times. It is still swallowed and counted by `make_push_handler.handler`'s broad `except Exception`, so the "never tear down the stream" guarantee is unchanged; only the pointless retries go away.

**Alternatives:** catching `AMQPError` only — rejected, transport failures surface as `OSError`/`RuntimeError`, not `AMQPError`. Removing the retry entirely — rejected, the bounded retry is the product's protection against transient broker hiccups.

### D3. Narrow `publish_donation` to `queue: str` (P3)

Change the signature to `publish_donation(broker: Broker, donation: Donation, queue: str)` and read `settings.amqp_queue` at the call site. `_publish_with_retry` becomes the boundary that unwraps `settings.amqp_queue` and passes it down; `make_push_handler` is unchanged.

**Alternatives:** narrowing the whole chain (`make_push_handler` → `_publish_with_retry` → `publish_donation`) to `queue` — considered, but the review flagged only `publish_donation`, and the factory/retry layers legitimately take `settings` for their own reasons; keeping this scoped to the flagged function avoids churn.

### D4. Make `log_donation` async and delete `_log_only` (P4)

Change `def log_donation` to `async def log_donation`, delete `_log_only`, and set `run()`'s default to `on_push: PushHandler = log_donation`. The push handler awaits it (`await log_donation(donation)`), and `test_log_donation_quotes_message` becomes async. The log line content is byte-for-byte identical; only the sync→async wrapper disappears.

**Alternatives:** keeping `log_donation` sync and inlining the default — rejected, a `PushHandler` must be awaitable, so an async wrapper would still be required. Renaming instead of deleting — rejected, `log_donation` is the accurate name for the shared operation.

### D5. `_async_main` returns an exit code, `run_cli` raises `SystemExit` (P5)

`_async_main` returns `int`: `0` on a clean run, `1` on broker-start or queue-declare failure (with the same `print` messages). The `raise SystemExit(1)` in those two `except` blocks becomes `return 1`; the outer `finally: await broker.stop()` still runs on the queue-declare path because it wraps the whole `try`. `run_cli` converts the code: `code = asyncio.run(_async_main(...))` then `if code: raise SystemExit(code)`. Observable exit codes (0/1/2) are unchanged; `SystemExit` now lives only in `run_cli`, not inside `_async_main`'s `try/finally`.

**Alternatives:** keeping `SystemExit` in `_async_main` — rejected, that is the finding under review. Returning a domain error object — rejected, an `int` exit code is the simplest faithful signal and matches `run_cli`'s existing `SystemExit(2)` convention.

### D6. `run()`'s six parameters stay flat (criterion-8 finding, not changed)

The review flags `run()` as having six parameters ("at the upper bound"). This is evaluated and left unchanged: `settings`, `gateway`, and `shutdown` are required dependencies, and `on_push`, `backoff`, and `stats` are injectable knobs with defaults. Bundling any of them into a struct would convert explicit, independently-injectable dependencies (criterion 3, currently satisfied) into a hidden bundle — trading criterion 3 away to satisfy the softer criterion-8 guideline. For a DI seam, flat explicit parameters are the correct design; grouping is churn without benefit.

## Risks / Trade-offs

- [P1 makes programming errors fatal] → a bug in `run_stream` or `on_push` now terminates the listener rather than looping. That is the intended fail-fast behavior; the process manager (systemd) restarts it. → The spec's "programming error terminates" scenario and a new test lock the propagate-on-programming-error path.
- [P2 drops retries for non-transient failures] → a serialization bug is recorded after one attempt rather than three. It is still logged and counted by the handler's broad `except Exception`. → A new test asserts a non-transient `publish` error is attempted exactly once.
- [P4 changes `log_donation` to async] → any sync caller must await it. The only callers are the push handler and one test. → Both are updated in the same change.
- [P5 changes `_async_main`'s return type] → direct callers (tests) must assert the return value instead of catching `SystemExit`. `run_cli` is the only production caller. → Two tests switch to `== 1`, one to `== 0`, and a new `run_cli` test locks the `SystemExit(1)` conversion.
- [No type checker] → the `int` return and async signature are not statically checked. → The duck-typed fakes and updated tests exercise both paths.

## Migration Plan

Small, additive source/test changes on a feature branch, merged via PR. No deployment coordination: the queue contract, heartbeat mtime, and CLI exit codes are unchanged; rollback is a revert. The `service` and `publisher` deltas must be synced to `openspec/specs/` after `production-readiness` (which introduces those capabilities) is synced.

## Open Questions

None — the exception surfaces and the current code shape were verified up front.
