## Purpose

Defines how the DonationAlerts gateway reports a failed stream attempt, so an
operator can diagnose repeated connection failures from the log alone without
reproducing them against the live gateway.

## Requirements

### Requirement: Failed stream attempt reports a non-empty cause

When a stream attempt fails, the gateway SHALL emit a single warning log line
that names the exception class, regardless of whether the exception carries a
message. An exception whose text renders empty SHALL NOT produce a log line
with a dangling empty value.

#### Scenario: Message-less exception

- **WHEN** a stream attempt fails with an exception whose text is empty, such as a bare `TimeoutError`
- **THEN** the warning log line names the exception class and carries no empty trailing value

#### Scenario: Exception with a message

- **WHEN** a stream attempt fails with an exception that carries text, such as a `ProtocolError` with a rejection reason
- **THEN** the warning log line names the exception class and includes that text

### Requirement: Failed stream attempt identifies the failing step

The gateway SHALL report which step of the attempt failed, distinguishing at
least the token exchange, the websocket handshake, the subscription, and the
message drain. Each failure is reported once, attributed to the step that was
executing when it occurred.

#### Scenario: Failure during the token exchange

- **WHEN** the token exchange request times out or is rejected
- **THEN** the warning names the token exchange as the failing step

#### Scenario: Failure during the subscription

- **WHEN** the subscribe request is rejected or the subscribe response signals an error
- **THEN** the warning names the subscription as the failing step

#### Scenario: Failure during the handshake or drain

- **WHEN** the websocket handshake fails or the connection drops while draining
- **THEN** the warning names the handshake or the drain, respectively, as the failing step

### Requirement: Diagnostics do not change retry behavior

Failure reporting SHALL NOT change the reconnect policy: a failed attempt
continues to yield an unsuccessful stream outcome and the listener continues to
retry with the existing backoff. No attempt SHALL be converted into a terminal
failure or a silent success by this change.

#### Scenario: Repeated failures keep retrying

- **WHEN** consecutive stream attempts fail, including with message-less exceptions
- **THEN** the listener keeps reconnecting on the existing backoff and the gateway does not exit or raise
