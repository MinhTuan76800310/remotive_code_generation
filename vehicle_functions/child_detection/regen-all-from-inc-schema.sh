#!/usr/bin/env bash
# Regenerate all ECU packages from inc_schema into generated/, then sync test_env.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
INC="$ROOT/inc_schema"
GEN="$ROOT/generated"
BMGEN="$ROOT/../../remotive-bm-compiler"

regen() {
  local yaml="$1" pkg="$2"
  local tmp
  tmp=$(mktemp -d)
  (cd "$BMGEN" && uv run bmgen generate "$yaml" --out "$tmp")
  rm -rf "$GEN/$pkg"
  cp -a "$tmp/$pkg" "$GEN/"
  rm -rf "$tmp"
  echo "  $pkg"
}

echo "=== bmgen generate -> generated/ ==="
regen "$INC/seatECU.yaml" seatecu
regen "$INC/driver_monitoringECU.yaml" drivermonitoringecu
regen "$INC/centralHPC.yaml" centralhpc
regen "$INC/cockpitHMIECU.yaml" cockpithmiecu
regen "$INC/airbagControlUnit.yaml" airbagcontrolunit

echo "=== sync -> test_env ==="
"$ROOT/sync-generated-to-test_env.sh"