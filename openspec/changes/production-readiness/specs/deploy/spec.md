## Purpose

Production deployment is reproducible and self-healing: wedged containers get restarted by an automated watchdog, credential files stay permission-locked, image builds are pinned, and CI/deploy gates are deterministic and serialized.

## ADDED Requirements

### Requirement: Unhealthy containers are restarted

The system SHALL restart the container when the Docker healthcheck reports it unhealthy, independently of whether the main process exits, and the README SHALL document this mechanism accurately.

#### Scenario: Container wedged but alive

- **WHEN** the container reports unhealthy while its process stays alive
- **THEN** an automated watchdog restarts the container

#### Scenario: README describes the watchdog

- **WHEN** the README describes how an unhealthy container is recovered
- **THEN** it describes the actual watchdog mechanism rather than claiming process-exit restart handles it

### Requirement: Credential files are permission-locked

The deploy process SHALL ensure the server-side environment file containing credentials is only readable by its owner.

#### Scenario: Deploy with permissive environment file

- **WHEN** a deploy runs and the environment file has group- or world-readable permissions
- **THEN** the deploy process tightens the permissions to owner-only

### Requirement: Image builds are reproducible

The image SHALL be built from pinned tooling and base-image versions, not floating tags.

#### Scenario: Image build

- **WHEN** the image is built
- **THEN** the uv tool version and the Python base image patch version are pinned in the Dockerfile

### Requirement: CI linting uses the locked toolchain

The CI quality gate SHALL run lint and format checks with the repository's locked lint version.

#### Scenario: CI quality run

- **WHEN** the CI quality workflow runs
- **THEN** the lint and format checks use the locked version from the project toolchain

### Requirement: Deploys do not interleave

The deploy workflow SHALL serialize concurrent runs so two pushes cannot deploy at the same time.

#### Scenario: Two pushes in quick succession

- **WHEN** a second deploy is triggered while a first deploy is still running
- **THEN** the second waits for the first to finish instead of running concurrently
