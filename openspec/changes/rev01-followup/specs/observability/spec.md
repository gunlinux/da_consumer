## ADDED Requirements

### Requirement: Publish-failure logs carry the root cause

The system SHALL include the underlying exception (message and traceback) in the error-level log emitted when a publish fails after its bounded retries, so operators can diagnose the reason (authentication, timeout, serialization, etc.) rather than only the fact of the failure.

#### Scenario: Publish fails after retries

- **WHEN** a donation publish fails after all retry attempts are exhausted
- **THEN** an error-level log is emitted that includes the underlying exception or traceback identifying why the publish failed
