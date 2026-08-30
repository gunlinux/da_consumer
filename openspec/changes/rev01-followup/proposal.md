## Why

`REV_01.md` reviewed the `dev` branch (the `testable-composition-root` + `production-readiness` changes) and found two robustness/observability regressions worth fixing before merge, plus a couple of cheap consistency gaps. Both regressions were introduced by the `Decimal` money conversion and the publish-retry logging change.

## What Changes

- **W1 — Malformed donation frames are skipped, not fatal.** `parse_donation` converts the DA amount string via `Decimal(str(...))`. A non-numeric amount now raises `decimal.InvalidOperation`, which is *not* a `ValueError`, so it escapes `parse_donation`'s `(KeyError, TypeError, ValueError)` guard and `_handle_text`'s `ProtocolError` guard. The result is that one bad donation tears down the stream (reconnect + backoff) instead of being skipped. Fix: add `InvalidOperation` to the caught tuple.
- **W2 — Publish-failure logs carry the root cause.** `make_push_handler` replaced `logger.exception` with `logger.error`, and the retry warning drops the exception, so operators can no longer see *why* a publish failed (auth? timeout? serialization?). Fix: `logger.exception` on the final failure and `exc_info` on the retry warning.
- **S1 — `Broker` protocol fully applied.** The `Broker` protocol introduced for the CLI seam is only used on `broker_factory`; `ensure_queue`, `make_push_handler`, `publish_donation`, and `_publish_with_retry` still annotate the concrete `RabbitBroker`, and the protocol's `publish` omits `persist`. Type the helpers against `Broker` and add `persist` to the protocol.
- **W3 — Pinned image toolchain verified.** Confirm `python:3.12.14-slim` and `ghcr.io/astral-sh/uv:0.12.7` exist and that the image builds.

**Deferred (deliberately out of scope):** S2 (align the sibling `production-readiness` spec wording "running count"/"threshold" with the implemented consecutive-count semantics — a doc edit in that change's own spec, best done at sync/archive time), S3 (drain-loop blocking note), S4 (`write_heartbeat` param rename), S5 (dedup the `redonats` name across deploy artifacts).

## Capabilities

### New Capabilities

- `protocol`: Robust donation-frame parsing — a malformed frame (including a non-numeric `amount`) is reported and skipped, and never tears down the donation stream.

### Modified Capabilities

- `observability`: Adds a requirement that publish-failure error logs include the underlying exception so the failure's root cause is diagnosable. (The base spec is introduced by the sibling `production-readiness` change in this branch and is not yet synced to `openspec/specs/`; this change only *adds* a requirement to it, so it must be synced after that change.)

## Impact

- `src/redonats/domain/protocol.py` — `parse_donation` catches `decimal.InvalidOperation` and maps it to `ProtocolError`.
- `src/redonats/application/publisher.py` — `Broker` protocol gains `persist`; broker-typed helpers (`ensure_queue`, `make_push_handler`, `publish_donation`, `_publish_with_retry`) are annotated against `Broker`; final publish failure uses `logger.exception` and the retry warning carries `exc_info`.
- `tests/test_protocol.py`, `tests/test_publisher.py` — new/updated tests for the malformed-amount path and the traceback-bearing log line.
- `Dockerfile` — no change expected; the pinned tags are verified to build (W3).
- No new runtime dependencies; `pyproject.toml` unchanged.
