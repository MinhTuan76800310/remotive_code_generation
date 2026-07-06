#!/usr/bin/env bash
# Generate Remotive topology from generated models + run pytest (getting_started pattern).
set -euo pipefail

cd "$(dirname "$0")"
COMPOSE="build/child_detection_generated/docker-compose.yml"

echo "=== remotive topology generate ==="
remotive topology generate \
  -f instances/main.instance.yaml \
  -f settings/can_over_udp.settings.instance.yaml \
  --name child_detection_generated \
  build

echo "=== docker compose --profile tester ==="
docker compose -f "$COMPOSE" --profile tester up --build --abort-on-container-exit tester
code=$?
docker compose -f "$COMPOSE" --profile tester rm -f tester 2>/dev/null || true
exit "$code"