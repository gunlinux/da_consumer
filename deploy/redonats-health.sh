#!/bin/bash
# =============================================================================
# redonats-health — restart the redonats container when Docker reports it
# unhealthy.
#
# Runs from deploy/redonats-health.service (a systemd timer). systemd's
# Restart=on-failure only reacts to process exit; a wedged-but-alive process
# is reported unhealthy by the image HEALTHCHECK and nothing restarts it
# without this watchdog. Restarts are restricted to the "unhealthy" status so
# a timer tick during an in-flight deploy cannot race a healthy container.
# =============================================================================
set -euo pipefail

CONTAINER="redonats"

STATUS="$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || true)"
if [ "$STATUS" != "unhealthy" ]; then
    exit 0
fi

echo "redonats-health: container '$CONTAINER' is unhealthy, restarting"
systemctl restart redonats
