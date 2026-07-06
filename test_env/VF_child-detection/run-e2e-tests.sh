#!/usr/bin/env bash
# End-to-end verification for bmgen-generated VF child-detection models.
#
# Runs the pytest integration suite inside the docker-compose "tester" profile.
# Tests inject signals via the topology broker restbus API and assert frames on
# COCKPIT / AIRBAG namespaces — same contract as manual remotive CLI flows.
#
# Prereqs:
#   - Stack already generated: build/vf_child_detection/docker-compose.yml
#   - Docker; Remotive Cloud auth if topology-broker requires it
#
# Usage:
#   ./run-e2e-tests.sh              # build + run tests, exit with pytest code
#   ./run-e2e-tests.sh --no-build   # reuse existing images
#
set -euo pipefail

cd "$(dirname "$0")"
COMPOSE_FILE="build/vf_child_detection/docker-compose.yml"
BUILD=1

for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD=0 ;;
    -h|--help)
      echo "Usage: $0 [--no-build]"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing $COMPOSE_FILE — run ./run-topology.sh first (or remotive topology generate)." >&2
  exit 1
fi

echo "=== E2E: docker compose --profile tester (abort on tester exit) ==="
if [[ "$BUILD" -eq 1 ]]; then
  docker compose -f "$COMPOSE_FILE" --profile tester up --build --abort-on-container-exit tester
else
  docker compose -f "$COMPOSE_FILE" --profile tester up --abort-on-container-exit tester
fi

EXIT_CODE=$?
echo
echo "=== Cleanup tester container (stack may still be up) ==="
docker compose -f "$COMPOSE_FILE" --profile tester rm -f tester 2>/dev/null || true

echo "=== E2E finished with exit code $EXIT_CODE ==="
exit "$EXIT_CODE"