## MODIFIED Requirements

### Requirement: Unexpected gateway errors do not stop the listener

The system SHALL treat an unexpected *transport* error raised by a stream attempt as a failed attempt: log it and continue the reconnect loop. A programming error (e.g. a type or value error) SHALL propagate and terminate the listener rather than being retried.

#### Scenario: Transient transport failure

- **WHEN** a stream attempt raises a transient transport error such as a dropped socket or a closed event loop
- **THEN** the error is logged and the loop continues with a reconnection instead of terminating

#### Scenario: Programming error in the stream

- **WHEN** a stream attempt raises a programming error
- **THEN** the error propagates and the listener terminates rather than retrying
