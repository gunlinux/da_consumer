## Context

See proposal.md — Why. The relevant current state is `AiohttpGateway.run_stream`
in `src/redonats/infrastructure/gateway.py`: it wraps the whole attempt in a
single `try` and, on an expected transport/protocol error, logs
`logger.warning("stream attempt failed: %s", exc)` before returning
`StreamOutcome(connected=False, ...)`. The four steps are separate private
coroutines (`_fetch_connection_token`, `_handshake`, `_create_subscription`,
`_subscribe`, `_drain`) called sequentially, and the `except` clause has no
knowledge of which one was running. Exceptions are limited to
`TimeoutError`, `aiohttp.ClientError`, `OSError`, `ProtocolError`; anything
else propagates and fails fast (per AGENTS.md).

Constraints: the `Gateway` protocol and `StreamOutcome` shape are a
dependency-injection seam used by `application/service.py` and tests, so their
signatures must not change. The DonationAlerts token/subscribe flow is
confirmed working and must not be altered.

## Goals / Non-Goals

**Goals:**

- Make each failed attempt's warning line self-explanatory from the log alone:
  which step failed and which exception class was raised, even when the
  exception text is empty.
- Keep the change inside the infrastructure adapter; no protocol or domain
  churn.

**Non-Goals:**

- Changing retry/backoff, adding fail-fast on auth errors, credential refresh,
  alerting, or metrics.
- Changing `StreamOutcome`, the `Gateway` protocol, or the exception set the
  adapter tolerates.
- Diagnosing the 2026-10-11 outage itself; this change only makes the next one
  legible.

## Decisions

**Track the failing step with a local label in `run_stream`, not a wrapper
type.** A `step: str` local updated immediately before each awaited step is the
smallest change: the existing `except` clause logs the label. Alternative
considered: a `_step(name, coro)` wrapper or an internal `_StepFailure`
exception — rejected as more machinery (a new type/propagating exception) than
the problem needs, which runs against the project's preference for the
simplest workable option. The label is internal only and never reaches
`StreamOutcome`.

**Render the cause as the exception class name plus the message when it is
non-empty.** A small helper produces `TimeoutError` for a message-less
exception and `ProtocolError: <text>` when `str(exc)` is non-empty. Alternative
considered: `%r`/`repr(exc)` — it avoids the empty-value problem but yields
noisy, less scannable output (`ClientConnectorError(...)`) for the common case;
the class name is the load-bearing datum. The empty-text guard is what removes
the dangling `failed:` seen in production.

**Keep the warning level, the tolerated exception set, and the single
`StreamOutcome(connected=False)` return unchanged.** This preserves the
reconnect contract in `application/service.py` and the existing test
expectations; the change is purely additive to the log line.

## Risks / Trade-offs

- [Log-line format changes] → Only the failure warning line changes; the
  observability contract covers donation key=value lines and the heartbeat, not
  the failure line's exact text. Keep the existing `key=value`-ish shape
  (`step=... error=...`) so any operator greps keep working, and assert the
  new shape in tests.
- [Step label drifts from the code as steps are added] → The label is set
  immediately adjacent to each awaited call, so a new step without a label is
  visible in review; tests cover one failure per step.
- [`TimeoutError` ambiguity] → On Python 3.12 `asyncio.TimeoutError` is
  `TimeoutError`, and the class name is all we can report; the step label
  disambiguates which timeout fired, which is the information that was missing.
