## Context

See proposal.md — Why. The two regressions sit in code just merged on this branch:

- `parse_donation` (`domain/protocol.py`) now builds the amount with `Decimal(str(data["amount"]))`. Its guard is `except (KeyError, TypeError, ValueError)`, but `Decimal("abc")` raises `decimal.InvalidOperation`, which is a `DecimalException`/`ArithmeticError`, **not** a `ValueError` (verified). The error escapes the `_handle_text` → `run_stream` → `run` chain and is treated as an "unexpected gateway failure", tearing down the stream. The previous `float(...)` raised `ValueError`, which was caught.
- `make_push_handler` (`application/publisher.py`) switched the final publish failure from `logger.exception` to `logger.error`, and `_publish_with_retry` logs the per-attempt warning without `exc_info`, dropping the root-cause detail.

Additional context:

- The `Broker` protocol was added by the composition-root change but is only used for the `broker_factory` type in `cli.py`; the broker-consuming helpers still annotate the concrete `RabbitBroker`, and the protocol's `publish` omits `persist` even though `publish_donation` passes it.
- CI has no type-checker (ruff + pytest only), so the `Broker` typing is documentation-grade, but it should still be self-consistent.
- The `protocol` capability is new (no sibling spec defines it). The `observability` capability is introduced by the sibling `production-readiness` change; this change only adds a requirement to it and must be synced after it.

## Goals / Non-Goals

**Goals:**

- Restore the "one bad frame never tears down the stream" invariant for the `amount` field specifically (W1).
- Restore diagnosable publish failures via the traceback in the error log (W2).
- Make the `Broker` protocol the real seam by typing the broker-consuming helpers against it and adding `persist` (S1).
- Confirm the pinned image toolchain versions build (W3).

**Non-Goals:**

- No change to the queue contract, heartbeat mtime semantics, reconnect policy, or the publish-swallowing/fail-soft split.
- No change to the "consecutive failure counter" behavior (S2 in the review is a doc wording fix in the sibling change, deferred to archive time).
- No spool/dead-letter path, no metrics infra, no `sd_notify`/WatchdogSec.

## Decisions

### D1. Catch `decimal.InvalidOperation` in `parse_donation` (W1)

Add `InvalidOperation` (imported from `decimal`) to the existing `except (KeyError, TypeError, ValueError)` tuple in `parse_donation`. This converts a non-numeric amount into the same `ProtocolError("donation payload misses required fields: ...")` path as any other malformed field, which `_handle_text` already skips.

**Alternatives:** pre-validating the amount with a regex — rejected, duplicates `Decimal`'s own validation and is more code. Catching `ArithmeticError` broadly — rejected, too wide (would also mask genuine decimal overflow). Catching `InvalidOperation` only — chosen, it is the exact exception `Decimal` raises for an unparseable string.

### D2. `logger.exception` on final failure + `exc_info` on retry warning (W2)

In `make_push_handler`, replace the final `logger.error(...)` with `logger.exception("failed to publish donation id=%d after %d attempts", ...)`. In `_publish_with_retry`, add `exc_info=True` to the per-attempt `logger.warning` so the intermediate failure is also visible.

**Alternatives:** logging `{exc!r}` inline — rejected, loses the traceback location. Keeping `logger.error` — rejected, that is the regression under review.

### D3. Apply the `Broker` protocol and add `persist` (S1)

Add `persist: bool = False` to `Broker.publish`'s signature, and change the annotations on `ensure_queue`, `make_push_handler`, `publish_donation`, and `_publish_with_retry` from `RabbitBroker` to `Broker`. `make_broker` keeps returning `RabbitBroker` (it structurally satisfies `Broker`).

**Alternatives:** keeping `RabbitBroker` annotations — rejected, leaves the seam decorative and forces test fakes to pretend to be `RabbitBroker`. Moving the protocol to `gateway.py` — rejected, the broker's home is `publisher.py`.

### D4. Verify the pinned toolchain (W3)

Confirm the tags `python:3.12.14-slim` and `ghcr.io/astral-sh/uv:0.12.7` resolve and that `docker build` (or `uv sync --locked` as a sanity check) succeeds. If a tag is wrong, pin the correct one. No code change unless verification fails.

**Alternatives:** reverting to floating tags — rejected, that undoes the reproducibility fix.

## Risks / Trade-offs

- [W1 fix masks other decimal errors] → `InvalidOperation` is the precise exception for unparseable strings; genuine overflow of a huge amount is out of scope for donation money, and the existing `ProtocolError` wrapping is the documented behavior.
- [W2 adds traceback noise] → the traceback appears only on a publish failure that already exhausted retries, which is an abnormal, operator-actionable event, not routine noise.
- [S1 is untested by mypy] → CI has no type-checker, so the annotations are documentation-grade; the existing duck-typed fakes already satisfy `Broker`, and the tests exercise every method.
- [W3 pin verification is manual] → flagged as a task with an explicit verify command; a bad pin would otherwise fail only on the next `main` deploy.

## Migration Plan

Small, additive source/test changes on a feature branch, merged via PR. No deployment coordination: the queue contract, heartbeat mtime, and CLI exit codes are unchanged. Rollback is a revert. The `protocol` spec is new; the `observability` delta must be synced to `openspec/specs/` after `production-readiness` (which introduces the `observability` capability) is synced.

## Open Questions

None — the exception hierarchy was verified up front, and the pinned-tag verification is a task-level check that does not change the approach or the specs.
