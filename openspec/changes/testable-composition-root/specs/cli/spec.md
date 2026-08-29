## Purpose

Defines the CLI composition root contract: startup sequence, exit codes, signal-driven shutdown, and injectable seams that make the wiring unit-testable without live DonationAlerts or RabbitMQ infrastructure.

## ADDED Requirements

### Requirement: CLI validates configuration before starting

The CLI SHALL load configuration from the environment and, when required settings are missing or invalid, print a configuration error message and exit with code 2 without starting the listener.

#### Scenario: Missing required environment variables

- **WHEN** the CLI starts with `DA_USER_ID`, `DA_ACCESS_TOKEN` or `AMQP_DSN` unset
- **THEN** the CLI prints a configuration error message and exits with code 2

#### Scenario: Invalid numeric settings

- **WHEN** `DA_RECONNECT_MAX_DELAY` or `AMQP_RECONNECT_DELAY` is not a number
- **THEN** the CLI prints a configuration error message and exits with code 2

### Requirement: CLI exits 1 when RabbitMQ is unreachable

The CLI SHALL print a connection error message and exit with code 1 when the RabbitMQ broker cannot be started.

#### Scenario: Broker start fails

- **WHEN** the broker fails to start
- **THEN** the CLI prints an error message and exits with code 1

### Requirement: CLI starts the donation listener

The CLI SHALL, after configuration succeeds, start the broker, declare the durable queue, install SIGTERM and SIGINT shutdown handlers, run the donation stream until shutdown is requested, remove the handlers, and stop the broker.

#### Scenario: Stream runs until shutdown

- **WHEN** the broker starts successfully, the queue is declared, and the stream runs until shutdown is requested
- **THEN** the CLI starts the broker, declares the durable queue, installs the shutdown handlers, runs the stream, removes the handlers, and stops the broker

#### Scenario: Broker is stopped when the stream raises

- **WHEN** an unexpected error aborts the donation stream
- **THEN** the CLI still stops the broker before exiting

### Requirement: Composition root supports injected components

The composition root SHALL expose the async startup sequence as an injectable operation accepting a broker factory, a gateway, and a signal sequence, defaulting to the production components, so the full startup and shutdown sequence can be exercised in unit tests without live infrastructure or OS signal handlers.

#### Scenario: Tests run the full lifecycle with fakes

- **WHEN** a test invokes the startup sequence with a fake broker factory, a fake gateway, an empty signal sequence, and requests shutdown
- **THEN** the sequence starts the fake broker, declares the queue, runs the fake stream, and stops the fake broker without registering OS signal handlers or touching the network
