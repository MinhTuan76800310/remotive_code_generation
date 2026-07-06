#!/usr/bin/env bash
# Copy bmgen output from generated/ into topology/models/*/python for Remotive E2E tests.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
GEN="$ROOT/generated"
TOP="$ROOT/topology/models"

copy_pkg() {
  local pkg="$1"
  local model_dir="$2"
  local dst="$TOP/$model_dir/python"
  rm -rf "$dst/$pkg"
  cp -a "$GEN/$pkg" "$dst/"
  echo "  $GEN/$pkg -> $dst/"
}

echo "=== Sync generated -> topology/models ==="
copy_pkg seatecu seat_ecu
copy_pkg drivermonitoringecu driver_monitoring_ecu
copy_pkg centralhpc central_hpc
copy_pkg cockpithmiecu cockpit_hmi_ecu
copy_pkg airbagcontrolunit airbag_control_unit

echo "=== Patch central_hpc CAD_logic (inc_schema weights + self.* fix) ==="
export TOP
python3 <<'PY'
from pathlib import Path
import os
import re

path = Path(os.environ["TOP"]) / "central_hpc/python/centralhpc/__main__.py"

text = path.read_text()
# Remove duplicate CameraInput handler block if present
text = re.sub(
    r"(\s+dms_cpd_can_0\.create_input_handler\(\s*\n\s*\[filters\.FrameFilter\(\"CameraInput\"\)\],\s*\n\s*centralhpc\.CAD_logic,\s*\n\s*\),)\s*\n\s*dms_cpd_can_0\.create_input_handler\(\s*\n\s*\[filters\.FrameFilter\(\"CameraInput\"\)\],\s*\n\s*centralhpc\.CAD_logic,\s*\n\s*\),",
    r"\1",
    text,
    count=1,
)
# Replace broken sum_expr / threshold with inc_schema-aligned block
old = re.search(
    r'async def CAD_logic\(self, frame: Frame\) -> None:.*?await self\.cpd_can_0\.restbus\.update_signals\(\s*\n\s*\(\"ChildAlert\.ChildAlertActive\".*?\),\s*\n\s*\)',
    text,
    re.DOTALL,
)
if not old:
    raise SystemExit("CAD_logic block not found — manual merge required")
new_body = '''async def CAD_logic(self, frame: Frame) -> None:
        if "SeatInput.SeatOccupied" in frame.signals:
            self._seat_input_latched = bool(frame.signals["SeatInput.SeatOccupied"])
        if "CameraInput.ChildDetectedByCamera" in frame.signals:
            self._camera_input_child_detected_by_camera_latched = bool(frame.signals["CameraInput.ChildDetectedByCamera"])
        if "AirbagStatusReport.AirbagStatus" in frame.signals:
            self._airbag_status_report_latched = bool(frame.signals["AirbagStatusReport.AirbagStatus"])
        _weighted_sum = (
            1.0 * (1 if self._seat_input_latched else 0)
            + 1.0 * (1 if self._camera_input_child_detected_by_camera_latched else 0)
            + 2.0 * (1 if self._airbag_status_report_latched else 0)
        )
        await self.cpd_can_0.restbus.update_signals(
            ("ChildAlert.ChildAlertActive", 1 if _weighted_sum >= 3.0 else 0),
        )'''
text = text[: old.start()] + new_body + text[old.end() :]
path.write_text(text)
print("  patched", path)
PY

echo "Done. Regenerate compose: cd topology && remotive topology generate ..."