## Purpose

Reliable donation delivery to RabbitMQ: persistent messages that survive broker restarts, bounded retry with surfaced failures, decimal-safe money handling, and clean startup errors.

## ADDED Requirements

### Requirement: Donations survive broker restarts

The system SHALL publish each donation to the durable queue with message persistence enabled, so a broker restart does not drop messages still sitting in the queue.

#### Scenario: Broker restarts after publish

- **WHEN** a donation has been published to the queue and the broker restarts
- **THEN** the queued donation is still delivered to consumers after the broker comes back

### Requirement: Publish failures are retried

The system SHALL retry a failed publish a bounded number of times with a short delay before giving up on the message, so a transient broker hiccup does not lose a donation outright.

#### Scenario: Broker temporarily unavailable

- **WHEN** the broker rejects or cannot accept a publish
- **THEN** the system retries the publish up to a bounded number of times and, if it still fails, records the failure instead of silently dropping the donation

### Requirement: Repeated publish failures are surfaced

The system SHALL track a running count of publish failures and SHALL emit an error-level log when the count crosses a threshold, so sustained donation loss cannot persist unnoticed.

#### Scenario: Sustained broker outage

- **WHEN** publishes keep failing across an extended outage
- **THEN** the failure count is visible in the heartbeat data and an error-level log line is emitted

### Requirement: Money amounts are decimal-safe

The system SHALL represent donation amounts as decimal values internally while publishing them as JSON numbers, preserving the existing queue contract for downstream consumers.

#### Scenario: Donation with decimal amount

- **WHEN** a donation of 12.5 arrives and is published
- **THEN** the published payload contains the JSON number 12.5 and the value is handled without binary floating-point arithmetic

### Requirement: Queue declaration failures exit cleanly

The system SHALL, when the queue cannot be declared at startup, print a concise error message and exit with a failure code instead of a raw traceback.

#### Scenario: Queue declaration fails

- **WHEN** the broker is reachable but the durable queue cannot be declared
- **THEN** the process prints a concise error message and exits with code 1
