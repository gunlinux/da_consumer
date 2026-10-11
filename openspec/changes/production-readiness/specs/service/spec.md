## Purpose

Robust reconnect-loop behavior: the backoff engages after short-lived "connected" streams, connect failures tear down cleanly, and unexpected gateway errors never stop the listener.

## ADDED Requirements

### Requirement: Reconnect backoff engages after short-lived streams

The system SHALL only reset the reconnect attempt counter when a stream attempt both connected and lasted at least a minimum duration; shorter "connected" attempts SHALL keep the backoff growing instead of resetting to the base delay.

#### Scenario: Stream connects but dies quickly

- **WHEN** a stream attempt connects successfully but ends after less than the minimum duration
- **THEN** the reconnect delay continues to grow rather than resetting to the base delay

#### Scenario: Sustained stream

- **WHEN** a stream attempt connects and runs for at least the minimum duration
- **THEN** the reconnect attempt counter resets so the next delay is the base delay

### Requirement: Connect failures clean up the listener

The system SHALL, when opening the gateway connection fails, stop the heartbeat and release gateway resources so no background task or open resource leaks.

#### Scenario: Gateway connection fails at startup

- **WHEN** the gateway connection attempt raises
- **THEN** the heartbeat stops being written, the gateway is closed, and the listener shuts down without orphaned tasks

### Requirement: Unexpected gateway errors do not stop the listener

The system SHALL treat an unexpected error raised by a stream attempt as a failed attempt: log it and continue the reconnect loop.

#### Scenario: Stream attempt raises

- **WHEN** a stream attempt raises an unexpected exception
- **THEN** the exception is logged and the loop continues with a reconnection instead of terminating
