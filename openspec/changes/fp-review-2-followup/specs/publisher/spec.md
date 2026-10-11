## MODIFIED Requirements

### Requirement: Publish failures are retried

The system SHALL retry a *transient* publish failure a bounded number of times with a short delay before giving up on the message, so a transient broker hiccup does not lose a donation outright. A non-transient failure (e.g. a payload that cannot be serialized) SHALL NOT be retried.

#### Scenario: Broker temporarily unavailable

- **WHEN** the broker rejects or cannot accept a publish due to a transient broker or transport failure
- **THEN** the system retries the publish up to a bounded number of times and, if it still fails, records the failure instead of silently dropping the donation

#### Scenario: Non-transient publish failure

- **WHEN** a publish fails for a reason unrelated to broker or transport availability
- **THEN** the system does not retry the publish and records the failure
