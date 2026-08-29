## Purpose

Logs and heartbeat data are parseable and reveal stream and publish health, so outages are visible without external metrics infrastructure.

## ADDED Requirements

### Requirement: Log values are parseable

The system SHALL emit structured key=value log lines in which free-text values, such as donation messages, are quoted so whitespace and special characters cannot break line-based parsing.

#### Scenario: Donation message with spaces

- **WHEN** a donation message contains spaces or quotes
- **THEN** the log line still parses as key=value with the message value intact

### Requirement: Heartbeat exposes stream and publish counters

The system SHALL write heartbeat data containing a timestamp, the number of donations received, the number of publish failures, and the time of the last donation, while continuing to touch the heartbeat file on the existing cadence.

#### Scenario: Heartbeat after donations and failures

- **WHEN** donations have been received and some publishes have failed
- **THEN** the heartbeat data reflects both counts and the last-donation time

### Requirement: Periodic health summary

The system SHALL periodically log a summary line reporting donation and publish-failure counts so long-running outages become visible in the logs.

#### Scenario: Summary after a period of activity

- **WHEN** the listener has been running for a summary period during which donations were received and publishes failed
- **THEN** an info-level log line reports the donation and publish-failure counts for the period
