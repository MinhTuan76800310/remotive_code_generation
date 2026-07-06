#!/usr/bin/env bash
# Copy bmgen output from generated/ into test_env/VF_child-detection/models/*/python/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
GEN="$ROOT/generated"
TE="$ROOT/../../test_env/VF_child-detection/models"

copy_pkg() {
  local pkg="$1"
  local model_dir="$2"
  local dst="$TE/$model_dir/python"
  rm -rf "$dst/$pkg"
  cp -a "$GEN/$pkg" "$dst/"
  echo "  $GEN/$pkg -> $dst/"
}

echo "=== generated/ -> test_env/VF_child-detection/models ==="
copy_pkg seatecu seat_ecu
copy_pkg drivermonitoringecu driver_monitoring_ecu
copy_pkg centralhpc central_hpc
copy_pkg cockpithmiecu cockpit_hmi_ecu
copy_pkg airbagcontrolunit airbag_control_unit

DMS_MAIN="$TE/driver_monitoring_ecu/python/drivermonitoringecu/__main__.py"
python3 <<PY
from pathlib import Path
p = Path("$DMS_MAIN")
t = p.read_text()
if 'os.environ.get("WS_CAMERA_URL"' not in t:
    if "import os\n" not in t:
        t = t.replace("import asyncio\n", "import asyncio\nimport os\n", 1)
    t = t.replace(
        'ws_url = "ws://localhost:1122"',
        'ws_url = os.environ.get("WS_CAMERA_URL", "ws://localhost:1122")',
    )
    p.write_text(t)
    print("  patched WS_CAMERA_URL in", p)
PY

echo "Done."