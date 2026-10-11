## Why

`FP_REVIEW_1.md` (the `check-fp` functional-purity audit) found the layering is working as intended: `domain/` is 100% pure, and 24 of 25 🔴 findings are *intentional boundary I/O* correctly confined to the infrastructure/application/cli layers. Four findings remain actionable without disturbing that deliberate boundary design — two 🟢 suggestions (a redundant `Decimal` conversion and a bare `RuntimeError`) and two "worth attention" items (direct `Stats` field mutation from the push handler and an ambient `time.time()` read inside `Stats.record_donation`).

## What Changes

- **P1 — Amount is normalized exactly once.** `parse_donation` no longer pre-converts the amount with `Decimal(str(...))`; `Donation.__post_init__` becomes the single place that normalizes the amount, removing the double decimal-string conversion. *(pure refactor — no spec-level behavior change)*
- **P2 — Not-connected gateway raises a domain error.** `AiohttpGateway._http` raises `ProtocolError` instead of a bare `RuntimeError` when the HTTP session is missing, so a gateway used before `connect()` reports a failed stream attempt rather than an unexpected error.
- **P3 — `Stats` mutation is encapsulated.** `Stats` gains named `record_publish_failure` / `record_publish_success` methods; the push handler no longer assigns `stats.publish_failures` directly. *(pure refactor — no spec-level behavior change)*
- **P4 — `Stats.record_donation` is deterministic.** The donation arrival timestamp is passed in as an explicit argument instead of being read from ambient `time.time()` inside the method. *(pure refactor — no spec-level behavior change)*

No breaking changes. No change to the queue contract, reconnect policy, heartbeat-mtime semantics, or the publish-swallowing/fail-soft split.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `gateway`: A gateway used before it is connected reports a domain `ProtocolError` and surfaces as a failed stream attempt (`connected=False`) instead of an unexpected `RuntimeError`. (Base spec introduced by the sibling `production-readiness` change; sync after it.)

P1, P3, and P4 are pure internal refactors with no externally-visible behavior change (the parsed `Donation`, the counters, and the heartbeat data are byte-for-byte equivalent), so they are captured in `design.md` and `tasks.md` but introduce no spec delta.

## Impact

- `src/redonats/domain/protocol.py` — `parse_donation` passes the raw amount through; the `Decimal` import is dropped (keeps `InvalidOperation`).
- `src/redonats/infrastructure/gateway.py` — `_http` raises `ProtocolError("gateway is not connected")`; a not-connected stream attempt now reports `connected=False` rather than propagating.
- `src/redonats/application/service.py` — `Stats.record_donation(now)` takes the timestamp; new `record_publish_failure` / `record_publish_success` methods.
- `src/redonats/application/publisher.py` — `make_push_handler` calls the `Stats` methods and reads `time.time()` at the boundary instead of mutating fields.
- `tests/test_protocol.py`, `tests/test_gateway.py`, `tests/test_service.py`, `tests/test_publisher.py` — new/updated tests for single normalization, the not-connected path, and the deterministic `Stats` methods.
- No new runtime dependencies; `pyproject.toml` unchanged.
