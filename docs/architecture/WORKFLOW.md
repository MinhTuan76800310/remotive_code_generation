# Workflow — Remotive Behavioral Model Compiler

> **Schema version**: `service_oriented` — namespace_types map + multi-output handlers
> **Last updated**: 2026-07-06

## Developer Workflow

### Step-by-step: From Spec to Verified Code

```text
1. Write YAML spec          →  vehicle_functions/child_detection/seat_ecu.yaml
2. Parse & validate         →  uv run bmgen generate seat_ecu.yaml --out /tmp/out/
3. Verify generated code    →  diff /tmp/out/seatecu/__main__.py against expected
4. If byte-identical → commit →  git add && git commit
5. If diff → fix spec       →  Edit YAML spec, re-run from step 2
```

### Step 1: Write YAML Spec

**Child detection (current)**: specs live under `vehicle_functions/child_detection/inc_schema/` — one **ECU entry** YAML per model (`seatECU.yaml`, `centralHPC.yaml`, …) with `ecu:` + `namespace_types:` + `software_components:` listing SWC fragment files (e.g. `SWC_CAD_logic.yaml` with `WeightedLogOdds`).

**Legacy single-file** specs still use `model:` + `namespace_types:` + `handlers:`:

The developer creates a YAML file describing ECU behavior. The `service_oriented` schema uses a flat `namespace_types:` map instead of the old `namespaces:` list:

```yaml
# vehicle_functions/child_detection/seat_ecu.yaml
model:
  name: SeatECU
  ecu_name: SEAT

namespace_types:
  SEAT-CpdCan0: can

handlers:
  - name: on_seat_occupancy
    pattern: ThresholdMapping
    threshold: 8
    operator: ">="
    true_when: below
    input:
      namespace: SEAT-CpdCan0
      frame_filter: SeatWeightSensor
      signal: SeatWeightSensor.WeightKg
    output:
      - namespace: SEAT-CpdCan0
        signals:
          - SeatInput.SeatOccupied
```

Key differences from the old schema:
- `namespace_types:` replaces `namespaces:` — just name → type, no role/restbus declaration
- `output:` is a **list** (one-element for single-output, multi-element for fan-out)

### Step 2: Generate Code

```bash
cd vehicle_functions/child_detection
./regen-all-from-inc-schema.sh
# or per ECU:
cd remotive-bm-compiler
uv run bmgen generate ../vehicle_functions/child_detection/inc_schema/centralHPC.yaml --out /tmp/out
```

This produces:
```text
generated/
├── seatecu/
│   ├── __init__.py
│   ├── __main__.py        # Complete behavioral model
│   └── log.py             # Logging configuration
```

The `__main__.py` contains the complete Remotive Behavioral Model Python code.

### Step 3: Verify Byte-Identical Diff

```bash
diff generated/seatecu/__main__.py \
  ../test_env/VF_child-detection/models/seat_ecu/python/seatecu/__main__.py
# Expected: no output (files are identical)
```

### Step 4: Run Integration Tests

```bash
cd test_env/VF_child-detection
./run-e2e-tests.sh
# Expected: 9 passed (8 K-map + airbag chain); logs INJECT / EXPECTED / ACTUAL per case

# Dashboard + one case per Enter (http://localhost:8080):
./run-dashboard-interactive.sh
```

Tests follow **getting_started** (`restbus.update_signals` + `capture_frames.wait_for_frame`). Oracle: `cad_expected()` from `inc_schema/SWC_CAD_logic.yaml` (weights 1/1/2, threshold 3.0) vs `HmiChildWarning.ChildAlertActive`.

### Step 5: Commit

```bash
git add vehicle_functions/child_detection/seat_ecu.yaml
git commit -m "migrate(seat_ecu): namespace_types + output list"
```

## Command Flow

```text
bmgen generate <yaml> --out <dir>
  │
  ▼ parser.py: read YAML → raw dict
  │
  ▼ builder.py: raw dict → IR dataclasses
  │   ├── _build_handlers: normalize output dict/list → output_groups
  │   ├── _build_websocket_listeners
  │   ├── _infer_namespaces: collect refs → derive role → auto-create restbus
  │   ├── _build_reset_handler (uses inferred namespaces)
  │   ├── validate_namespace_types(spec, ir): rules 14/15/16
  │   ├── validate(ir): rules 1-13
  │   └── _apply_value_exprs: stamp value_expr on every output signal
  │
  ▼ registry.py: for each handler/ws, lookup recipe by pattern name
  │
  ▼ recipe.validate(handler_ir): confirm handler IR matches recipe requirements
  │
  ▼ recipe.build_context(handler_ir): produce template context dict
  │
  ▼ context_builder.py: _merge_recipe_context
  │   ├── Build output_groups list (canonical multi-output shape)
  │   ├── Reconstruct flat fields from output_groups[0] (backward-compat)
  │   └── Merge recipe-specific fields
  │
  ▼ python_generator.py: render Jinja2 templates
  │   ├── Pre-render each handler body (multi-output branch if needed)
  │   ├── Pre-render websocket bodies
  │   ├── Pre-render reset handler body
  │   └── Render main.py.j2 with all pre-rendered bodies
  │
  ▼ Write files to --out dir


bmgen verify <dir>
  │
  ▼ structural.py: T1 checks (file, syntax, imports, signatures, refs)
  │   ─── if any T1 FAIL → stop, return report with FAIL status
  │
  ▼ behavioral.py: T2 checks (fake frame, mock restbus, expected outputs)
  │   ─── if any T2 FAIL → stop, return report with FAIL status
  │
  ▼ composition.py: T3 checks (duplicates, conflicts, lifecycle)
  │
  ▼ report.py: aggregate all checks → VerificationReport JSON


bmgen recipes
  │
  ▼ registry.py: list all registered recipes
  │
  ▼ print recipe names, descriptions
```

## Example CLI Usage

### Multi-Output ThresholdMapping (new_schema.yaml)

```bash
# Generate code
uv run bmgen generate ../new_schema.yaml --out generated/

# Inspect the generated handler
grep -A 10 "async def on_seat_occupancy" generated/seatecu/__main__.py
# Output:
#     async def on_seat_occupancy(self, frame: Frame) -> None:
#         seat_weight_sensor_signal = frame.signals["SeatWeightSensor.WeightKg"]
#         await self.cpd_can_0.restbus.update_signals(
#             ("SeatInput.SeatOccupied", 1 if not (seat_weight_sensor_signal >= 8) else 0),
#         )
#         await self.cpd_can_1.restbus.update_signals(
#             ("SeatInput.SeatOccupiedBackup", 1 if not (seat_weight_sensor_signal >= 8) else 0),
#         )

# Verify there are exactly 2 update_signals calls
grep -c "restbus.update_signals" generated/seatecu/__main__.py
# Expected: 2
```

### List Available Recipes

```bash
uv run bmgen recipes
# Output:
# DirectSignalMapping - Read input signal(s), write same value to output signals
# ToggleButtonState   - Toggle boolean state on button press
# PeriodicBlinkingOutput - Periodic async task with blinking output
# ThresholdMapping    - Compare analog signal against threshold, output 0 or 1
# LogicAnd            - Bitwise AND of two input signals
# LogicOr             - Bitwise OR of two input signals
# LogicXor            - Bitwise XOR of two input signals
# LogicNot            - Bitwise NOT of input signal
# WebsocketBridge     - Bridge external websocket stream onto CAN restbus
# WeightedLogOdds     - CAD weighted sum of latched bool inputs (multi-namespace fan-in)
```

## Local Development Workflow

```bash
# Clone and setup
git clone <repo>
cd remotive-bm-compiler
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
# Expected: 139 passed (2026-07-06)

# Generate and verify
uv run bmgen generate ../vehicle_functions/child_detection/seat_ecu.yaml --out _local_gen/
# ... inspect _local_gen/ ...

# Clean generated files
rm -rf _local_gen/
```

## Multi-Output Test Suite

```bash
# Run just the multi-output tests
pytest tests/test_multi_output.py -v
# Expected: 8 passed
#   TestMultiOutputIR::test_two_output_groups_inferred
#   TestMultiOutputIR::test_handler_has_two_output_groups
#   TestMultiOutputIR::test_value_expr_fans_out_to_all_groups
#   TestMultiOutputGeneratedCode::test_two_update_signals_calls_in_order
#   TestMultiOutputGeneratedCode::test_value_expr_appears_in_both_calls
#   TestMultiOutputGeneratedCode::test_dataclass_has_both_namespace_vars
#   TestMultiOutputGeneratedCode::test_generated_code_is_valid_python
#   TestSingleOutputStillByteIdentical::test_single_output_uses_flat_update_signals
```

## Migration Order (for converting old specs)

When migrating existing YAML specs from the old `namespaces:` schema:

1. Replace `namespaces:` list with `namespace_types:` map (just `name: type` per entry)
2. Wrap `output:` as a one-element list: `output: [{namespace: X, signals: [Y]}]`
3. Generate and diff against the previous output — must be byte-identical
4. Remove any namespace declarations that were never referenced (they'll now produce an orphan warning)

The builder accepts both old and new formats during the migration window. When `namespaces:` is present alongside/instead of `namespace_types:`, the old block is ignored (with a `DeprecationWarning`) and inference runs from `namespace_types:` alone. If only `namespaces:` is present (no `namespace_types:`), Invariant 14 (strict-required) is skipped — the old block already declares the namespaces explicitly.
