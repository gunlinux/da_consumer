# syntax=docker/dockerfile:1

# Pinned toolchain for reproducible builds: uv release and Python patch
# version are fixed, never floating tags.
FROM python:3.12.14-slim

# uv provides the lockfile-driven installer (single runtime stage, so the
# project venv always links to the image's own system Python).
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install locked dependencies first for layer caching.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Install the project itself (creates the `redonats` console script).
COPY src ./src
RUN uv sync --frozen --no-dev

# Run as an unprivileged user.
RUN groupadd --system redonats \
    && useradd --system --gid redonats --home /app redonats \
    && chown -R redonats:redonats /app

USER redonats

ENTRYPOINT ["redonats"]

# The listener writes /tmp/redonats.heartbeat every 15s while the event
# loop is alive; fail the healthcheck if the file is older than 90s.
# If DA_HEARTBEAT_PATH is overridden, update this path to match.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["sh", "-c", "test $(($(date +%s) - $(stat -c %Y /tmp/redonats.heartbeat))) -lt 90"]
