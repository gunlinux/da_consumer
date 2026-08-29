## Purpose

The DonationAlerts gateway adapter is fully unit-testable: the complete stream sequence (token exchange, websocket handshake, subscription, drain) runs against injected doubles with no network access.

## ADDED Requirements

### Requirement: Full stream flow runs against injected doubles

The system SHALL allow the complete stream sequence to be exercised against injected HTTP-session and websocket doubles, and SHALL use an injected session as-is without ever opening a real network session.

#### Scenario: Successful full flow with fake session

- **WHEN** the gateway runs a stream with injected session and websocket doubles returning valid canned responses and a donation frame
- **THEN** the stream reports a successful outcome and the donation is delivered to the push handler

#### Scenario: Token exchange fails

- **WHEN** the connection-token exchange fails with an HTTP error
- **THEN** the stream reports an unsuccessful outcome without raising

#### Scenario: No real session is created when one is injected

- **WHEN** a session double is injected and a stream attempt runs
- **THEN** the gateway uses the injected session and never constructs a real network session
