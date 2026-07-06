#!/usr/bin/env bash
# Start topology + Remotive web dashboard (http://localhost:8080), then run ONE pytest
# per keypress — watch signals on the UI while logs print INJECT / EXPECTED / ACTUAL below.
#
# Usage:
#   ./run-dashboard-interactive.sh
#   ./run-dashboard-interactive.sh --no-build
#
# Controls:
#   Enter     → run next K-map case in order (km_000 … km_111, then airbag chain, repeat)
#   1-8       → run that K-map case once, then back to prompt
#   9         → airbag-off chain once
#   a + Enter → all 9 tests
#   q + Enter → quit (stack keeps running)
#
set -euo pipefail

cd "$(dirname "$0")"
COMPOSE_FILE="build/vf_child_detection/docker-compose.yml"
BUILD=1

for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD=0 ;;
    -h|--help)
      sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
  esac
done

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "=== Generating topology (first time) ==="
  remotive topology generate \
    -f instances/main.instance.yaml \
    -f settings/can_over_udp.settings.instance.yaml \
    --name vf_child_detection \
    build
fi

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

echo "=== Starting stack + dashboard UI (profile ui) ==="
if [[ "$BUILD" -eq 1 ]]; then
  compose --profile ui up -d --build
else
  compose --profile ui up -d
fi

echo
echo "  Dashboard : http://localhost:8080"
echo "  Broker API: http://localhost:50051"
echo "  Watch     : HmiChildWarning.ChildAlertActive, ChildAlert, SeatInput, CameraInput"
echo

KMAP_IDS=(km_000 km_001 km_010 km_011 km_100 km_101 km_110 km_111)
STEP=0
N_KMAP=${#KMAP_IDS[@]}
TOTAL=$((N_KMAP + 1))

run_pytest() {
  local spec="$1"
  echo
  echo ">>> pytest $spec"
  echo ">>> (signals should update on http://localhost:8080)"
  echo
  compose --profile tester run --rm tester \
    pytest --broker_url=http://topology-broker.com:50051 -s -vv "$spec" || true
  echo
}

next_auto_case() {
  if [[ "$STEP" -lt "$N_KMAP" ]]; then
    local id="${KMAP_IDS[$STEP]}"
    STEP=$((STEP + 1))
    run_pytest "test_child_detection.py::test_cad_kmap_expected_matches_hmi_actual[$id]"
    return
  fi
  if [[ "$STEP" -eq "$N_KMAP" ]]; then
    STEP=$((STEP + 1))
    run_pytest "test_child_detection.py::test_driver_turn_airbag_off_propagates_to_actuator"
    return
  fi
  STEP=0
  next_auto_case
}

prompt() {
  echo "────────────────────────────────────────"
  echo " Enter = next case (${STEP}/${TOTAL} in cycle) | 1-8 = km_* | 9 = airbag | a = all | q = quit"
  printf "> "
}

while true; do
  prompt
  read -r choice || break
  choice=$(echo "$choice" | tr '[:upper:]' '[:lower:]' | xargs)

  case "$choice" in
    q|quit|exit)
      echo "Stack still up. Stop:"
      echo "  docker compose -f $COMPOSE_FILE --profile ui down"
      break
      ;;
    a|all)
      run_pytest "test_child_detection.py"
      ;;
    '')
      next_auto_case
      ;;
    [1-8])
      idx=$((choice - 1))
      id="${KMAP_IDS[$idx]}"
      run_pytest "test_child_detection.py::test_cad_kmap_expected_matches_hmi_actual[$id]"
      ;;
    9)
      run_pytest "test_child_detection.py::test_driver_turn_airbag_off_propagates_to_actuator"
      ;;
    km_*)
      run_pytest "test_child_detection.py::test_cad_kmap_expected_matches_hmi_actual[$choice]"
      ;;
    *)
      echo "Unknown: '$choice' (try Enter, 1-9, a, q)"
      ;;
  esac
done