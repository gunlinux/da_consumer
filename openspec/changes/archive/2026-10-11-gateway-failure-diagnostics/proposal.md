## Why

The gateway failure log is unreadable precisely when it matters most. On
2026-10-11 the production listener retried endlessly (`attempt 83`, ~42
minutes of 30s-cadence failures) emitting:

```
WARNING redonats.infrastructure.gateway stream attempt failed:
```

with nothing after the colon. `logger.warning("stream attempt failed: %s", exc)`
renders an empty string for message-less exceptions such as a bare
`TimeoutError` from the 30s HTTP/WS timeout. The log cannot distinguish a
timeout from an auth rejection, a DNS failure, or a protocol error, nor say
which step failed — so the operator cannot tell whether to wait, refresh a
token, or fix the network.

## What Changes

- The failure warning now identifies **which step** failed (token exchange,
  websocket handshake, subscription, or message drain) and names the
  **exception class**, so a message-less exception still produces a useful
  line.
- Non-empty exception text is still included; genuinely informative messages
  are not lost.
- Retry behavior is unchanged: the reconnect loop keeps retrying transient
  failures with exponential backoff. No fail-fast, no credential refresh, no
  alerting is introduced by this change.

## Capabilities

### New Capabilities

- `gateway`: the DonationAlerts gateway adapter reports each failed stream
  attempt with enough detail (failing step, exception class, elapsed time) to
  diagnose the cause from logs alone.

### Modified Capabilities

None. No existing `openspec/specs/` capability changes; this is a new
capability describing the gateway's failure-reporting contract.

## Impact

- `src/redonats/infrastructure/gateway.py`: the `run_stream` failure path and
  the exception handler around each step.
- `tests/test_gateway.py`: assertions that a failure logs the step and
  exception class, including for a message-less `TimeoutError`.
- Unchanged: the `StreamOutcome` shape, the `Gateway` protocol, the reconnect
  policy in `application/service.py`, the RabbitMQ publish path, and the
  DonationAlerts token/subscribe flow (which is confirmed working and must not
  be altered).
