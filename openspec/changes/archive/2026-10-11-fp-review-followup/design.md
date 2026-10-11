## Context

See proposal.md — Why. The four findings all sit in code that is already layered correctly, so the changes are small and localized:

- **P1** — `parse_donation` (`domain/protocol.py`) builds the amount with `Decimal(str(data["amount"]))`, but `Donation.__post_init__` (`domain/models.py`) re-normalizes via `Decimal(str(self.amount))`. The amount is decimal-string-converted twice. `protocol.py` imports `from decimal import Decimal, InvalidOperation`.
- **P2** — `AiohttpGateway._http` (`infrastructure/gateway.py`) raises `RuntimeError("gateway is not connected")`. `run_stream` already catches `(TimeoutError, aiohttp.ClientError, OSError, ProtocolError)` and returns `StreamOutcome(connected=False)`; `ProtocolError` is already imported in the module.
- **P3** — `make_push_handler.handler` (`application/publisher.py`) assigns `stats.publish_failures += 1` / `= 0` directly, while `Stats.record_donation()` already exists as the only named mutation method.
- **P4** — `Stats.record_donation` (`application/service.py`) reads ambient `time.time()` inside the method.

CI runs `ruff check` / `ruff format --check` / `pytest` only — there is no type-checker, so annotations are documentation-grade. The `gateway`, `service`, and `publisher` base specs are introduced by the sibling `production-readiness` change; `protocol` by the sibling `rev01-followup` change. None are yet synced to `openspec/specs/`.

## Goals / Non-Goals

**Goals:**

- Remove the redundant decimal conversion so the amount is normalized exactly once (P1).
- Replace the bare `RuntimeError` with a domain error and report the not-connected case through the normal failed-outcome path (P2).
- Encapsulate `Stats` mutation behind named methods so no caller reaches into the counters to write them (P3).
- Make `Stats.record_donation` deterministic by injecting the timestamp as an explicit argument (P4).

**Non-Goals:**

- `Stats` stays the one deliberate piece of mutable shared state — this change does not make it frozen or immutable.
- `Stats` fields stay public for reading (`_stats_payload` and `_heartbeat_loop` read them); only *mutation* is encapsulated.
- No new domain error type, no queue-contract/reconnect/heartbeat-mtime change, no publish-swallowing/fail-soft change.

## Decisions

### D1. Pass the raw amount through `parse_donation` (P1)

Change `amount=Decimal(str(data["amount"]))` to `amount=data["amount"]`, and drop the now-unused `Decimal` import (keep `InvalidOperation`). `Donation.__post_init__` becomes the single normalization point; it already handles `str`, `int`, `float`, and `Decimal` inputs via `Decimal(str(self.amount))`.

A non-numeric amount still raises `decimal.InvalidOperation` — but now from inside `Donation.__post_init__`, which runs within `parse_donation`'s `try`, so the existing `except (KeyError, TypeError, ValueError, InvalidOperation)` still maps it to `ProtocolError`. `test_parse_donation_raises_on_non_numeric_amount` guards this.

**Alternatives:** removing `__post_init__` and keeping the pre-conversion — rejected, `__post_init__` is the documented normalization for direct `Donation(...)` construction (tests build `Donation(amount=12.5)` directly) and is the correct single home. Regex pre-validation — rejected, duplicates `Decimal`'s own parsing.

### D2. Raise `ProtocolError` from `_http` (P2)

Change `raise RuntimeError("gateway is not connected")` to `raise ProtocolError("gateway is not connected")`. `ProtocolError` is already imported. Because `run_stream` catches `ProtocolError`, a stream attempt run before `connect()` now reports `StreamOutcome(connected=False)` instead of propagating; this is the fail-soft behavior the gateway spec describes.

This path only fires on misuse — `run()` always calls `gateway.connect()` before the loop and `close()` only after. The one behavioral consequence (unexpected → expected failure) is intentional and is locked by a new test.

**Alternatives:** `ConfigError` — rejected, "not connected" is not a config problem and it is not in `run_stream`'s catch tuple, so it would keep propagating. A new dedicated error type — rejected as over-engineering for a defensive invariant that never fires in normal operation; reusing the closest domain error matches the review's suggestion and keeps scope minimal.

### D3. Encapsulate publish-failure mutation (P3)

Add two methods to `Stats`: `record_publish_failure()` (`self.publish_failures += 1`) and `record_publish_success()` (`self.publish_failures = 0`). The handler calls these instead of assigning `stats.publish_failures` directly, so all counter mutation flows through named `Stats` operations. The reset-on-success ("consecutive failure") semantics are preserved.

**Alternatives:** making the fields private and exposing properties — rejected, read access spans `service.py` and the review only flagged the handler's direct *write*; the added churn buys nothing here.

### D4. Inject the timestamp into `record_donation` (P4)

Change `record_donation` to `record_donation(self, now: float)` and set `self.last_donation_at = now`. The handler imports `time` and calls `stats.record_donation(time.time())`, moving the ambient clock read to the boundary (the handler already performs logging and publishing I/O). `record_donation` becomes deterministic given its inputs. Epoch `time.time()` is kept (not `monotonic`) for consistency with `write_heartbeat`'s `ts`.

**Alternatives:** injecting a clock callable into `Stats(...)` — rejected, needs `dataclasses.field(default=..., compare=False)` machinery for the same benefit; an explicit parameter is the simpler FP idiom. Leaving `time.time()` in place — rejected, that is the finding under review.

## Risks / Trade-offs

- [P1 removes pre-validation] → the non-numeric path still raises `InvalidOperation` inside `__post_init__`, which is caught by `parse_donation`'s existing `except` tuple; the existing test guards it.
- [P2 turns a misuse case fail-soft] → only reachable when `run_stream` runs before `connect()`, which the real composition never does; a new gateway test pins the `connected=False` outcome.
- [P3/P4 are not type-checked] → CI has no type-checker; the duck-typed fakes and existing tests already exercise the counters, and new tests cover the deterministic signature.
- [P4 keeps a wall-clock read] → `time.time()` remains non-deterministic at the point of capture; the improvement is that `record_donation` itself no longer depends on hidden ambient state, which is the criterion under review.

## Migration Plan

Small, additive source/test changes on a feature branch, merged via PR. No deployment coordination: the queue contract, heartbeat mtime, and CLI exit codes are unchanged; rollback is a revert. The `gateway` delta must be synced to `openspec/specs/` after `production-readiness` (which introduces the `gateway` capability) is synced.

## Open Questions

None — the double-conversion mechanics and the `run_stream` exception handling were verified up front.
