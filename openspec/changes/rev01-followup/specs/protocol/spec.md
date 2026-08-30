## Purpose

Donation-frame parsing maps gateway push data onto the domain `Donation` model and reports malformed frames as `ProtocolError` so a single bad frame is skipped, never fatal to the stream.

## ADDED Requirements

### Requirement: Non-numeric amounts are reported as parse errors

The system SHALL treat a donation whose `amount` cannot be parsed as a decimal number as a malformed frame and SHALL surface it as a parse error (not as an unexpected crash), so the surrounding frame handler can skip it and keep the stream alive.

#### Scenario: Amount is not a number

- **WHEN** a donation frame carries an `amount` that is not a valid decimal number (e.g. an empty or non-numeric string)
- **THEN** parsing raises a parse error and the frame is skipped without terminating the stream

#### Scenario: Amount is numeric

- **WHEN** a donation frame carries a numeric `amount` (integer or decimal string)
- **THEN** parsing succeeds and the donation's amount is represented as a decimal value
