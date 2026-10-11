## ADDED Requirements

### Requirement: Gateway used before connection reports a failed attempt

The system SHALL report a stream attempt that runs before the gateway connection has been opened as a failed stream outcome rather than an unexpected error, and SHALL signal the missing connection with a domain error instead of a bare runtime error, so the reconnect loop applies its retry policy consistently.

#### Scenario: Stream attempt before connection

- **WHEN** a stream attempt runs before the gateway connection has been opened
- **THEN** the attempt reports a failed stream outcome instead of raising an unexpected error

#### Scenario: Missing connection is a domain error

- **WHEN** the gateway requires its HTTP connection but none is open
- **THEN** it raises a domain protocol error rather than a generic runtime error
