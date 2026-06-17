# Verifier Design — Remotive Behavioral Model Compiler

## 3-Layer Verification Architecture

The verifier operates in three sequential layers. Each layer must PASS before the next layer executes. This fail-fast design prevents wasting time on behavioral or composition checks when the code is structurally broken.

```text
Generated Python Code
        │
        ▼
  ┌─────────────┐
  │  T1: Structural │ ─── FAIL → Return report, stop
  │  Verifier      │ ─── PASS → Continue to T2
  └─────────────┘
        │
        ▼
  ┌─────────────┐
  │  T2: Behavioral │ ─── FAIL → Return report, stop
  │  Verifier      │ ─── PASS → Continue to T3
  └─────────────┘
        │
        ▼
  ┌─────────────┐
  │  T3: Composition │ ─── FAIL → Return report, stop
  │  Verifier      │ ─── PASS → Return PASS report
  └─────────────┘
```

## T1: Structural Verifier

**Purpose**: Verify that generated code is valid Python and has the correct structural form for a Remotive Behavioral Model.

**How it works**: T1 operates on the generated Python file(s) as static artifacts. It does not execute the code (except for import checks). It checks syntax, AST structure, and naming conventions.

### T1 Checks

| # | Check Name | Description | Implementation |
|---|------------|-------------|----------------|
| 1 | `file_exists` | Generated Python file exists at expected path | `os.path.isfile()` |
| 2 | `syntax_valid` | Python syntax is valid (no parse errors) | `ast.parse(file_content)` |
| 3 | `module_imports` | All required modules import successfully | Dynamic import in sandboxed subprocess: `importlib.import_module()` |
| 4 | `remotive_imports_present` | Required Remotive imports are in the file | AST grep for `from remotivelabs.broker import ...`, `from remotivelabs.topology.behavioral_model import ...`, `from remotivelabs.topology.namespaces.can import ...` |
| 5 | `handler_methods_async` | All handler methods are `async def` | AST grep: check `FunctionDef` nodes have `async` keyword for handler names |
| 6 | `handler_accepts_frame` | All handler methods accept a `frame` parameter with type annotation `Frame` | AST grep: check function signature has parameter named `frame` with annotation `Frame` |
| 7 | `namespace_refs_exist` | Namespace string literals in code match IR namespace names | AST grep: extract string literals from `CanNamespace()` calls, compare to IR namespace list |
| 8 | `output_has_restbus` | Output namespace has `restbus_configs` argument in `CanNamespace()` constructor | AST grep: for output namespace `CanNamespace()` calls, check `restbus_configs` keyword arg exists |
| 9 | `input_has_frame_filter` | Input handlers have `create_input_handler` with `FrameFilter` argument matching IR spec | AST grep: check `filters.FrameFilter("X")` strings match IR `input_frame_filter` values |
| 10 | `restbus_update_signals_used` | Handler body contains `await ...restbus.update_signals(...)` calls | AST grep: check for `restbus.update_signals` call pattern |
| 11 | `main_function_exists` | `async def main(avp: BehavioralModelArgs)` exists | AST grep: check function definition |
| 12 | `entry_point_exists` | `if __name__ == "__main__"` block with `BehavioralModelArgs.parse()` and `asyncio.run()` | AST grep: check main block structure |

### T1 Skip Conditions

- `novel_logic=True` handlers: T1 still checks structural form (stub handler exists, is async, accepts frame), but does NOT check `restbus.update_signals_used`
- Handlers that don't use `restbus` (e.g., future SOME/IP `notify` calls): T1 checks the appropriate output method instead

## T2: Behavioral Verifier

**Purpose**: Verify that generated handler methods produce correct output values when called with fake input frames.

**How it works**: T2 dynamically loads the generated Python module, creates mock objects (fake `Frame`, mock `restbus`), calls handler methods, and checks that mock `restbus.update_signals` received the expected signal-value tuples.

### Mock Infrastructure

```python
class FakeFrame:
    """Simulates a Remotive Frame with configurable signal values."""
    def __init__(self, signals: dict[str, float | int]):
        self.signals = signals

class MockRestbus:
    """Captures all update_signals calls for verification."""
    def __init__(self):
        self.calls: list[list[tuple[str, float | int]]] = []

    async def update_signals(self, *tuples: tuple[str, float | int]):
        self.calls.append(list(tuples))

class MockNamespace:
    """Namespace with mock restbus for output verification."""
    def __init__(self, name: str, restbus: MockRestbus):
        self.name = name
        self.restbus = restbus
```

### T2 Checks

| # | Check Name | Description | Implementation |
|---|------------|-------------|----------------|
| 1 | `handler_callable_with_fake_frame` | Handler can be called with a `FakeFrame` without crashing | Create `FakeFrame` with IR input signals → call handler → no exception |
| 2 | `mock_restbus_receives_calls` | `MockRestbus.update_signals` is called at least once | Check `mock_restbus.calls` is non-empty |
| 3 | `direct_signal_mapping_output_correct` | DirectSignalMapping: output signals match input signal value | For input signal value X, check all output tuples have value X |
| 4 | `direct_signal_mapping_output_signals_match` | DirectSignalMapping: output signal names match IR spec | Check tuple signal names match `OutputSignalIR.name` list |
| 5 | `toggle_button_press_once_enabled` | ToggleButtonState: first press (value=1) → state=True → outputs=1 | Create FakeFrame with signal=1 → call handler → check outputs are 1 |
| 6 | `toggle_button_press_twice_disabled` | ToggleButtonState: second press (value=1) → state=False → outputs=0 | Create model with initial state=True → FakeFrame signal=1 → call handler → check outputs are 0 |
| 7 | `toggle_button_press_zero_no_change` | ToggleButtonState: press with value=0 → no state change | Create FakeFrame with signal=0 → call handler → check no update_signals call |

### T2 Per-Pattern Behavioral Tests

**DirectSignalMapping test sequence**:
```python
# Given: IR spec for on_hazard_light with DirectSignalMapping
# Input: HazardLightButton.HazardLightButton
# Output: TurnLightControl.RightTurnLightRequest, TurnLightControl.LeftTurnLightRequest

fake_frame = FakeFrame({"HazardLightButton.HazardLightButton": 1.0})
mock_restbus = MockRestbus()
model = create_model_with_mocks(ir_spec, mock_restbus)
await model.on_hazard_light(fake_frame)

assert mock_restbus.calls[0] == [
    ("TurnLightControl.RightTurnLightRequest", 1.0),
    ("TurnLightControl.LeftTurnLightRequest", 1.0),
]
```

**ToggleButtonState test sequence**:
```python
# Given: IR spec for on_hazard_button with ToggleButtonState
# State: hazard_enabled (bool, initial=False)
# Input: HazardLightButton.HazardLightButton
# Output: TurnLightControl signals (1 if enabled, 0 if disabled)

# Test 1: Press once → enabled
model = create_model_with_mocks(ir_spec, mock_restbus)
fake_frame = FakeFrame({"HazardLightButton.HazardLightButton": 1})
await model.on_hazard_button(fake_frame)
assert mock_restbus.calls[0] == [("TurnLightControl.RightTurnLightRequest", 1), ("TurnLightControl.LeftTurnLightRequest", 1)]

# Test 2: Press again → disabled
mock_restbus.calls.clear()
fake_frame = FakeFrame({"HazardLightButton.HazardLightButton": 1})
await model.on_hazard_button(fake_frame)
assert mock_restbus.calls[0] == [("TurnLightControl.RightTurnLightRequest", 0), ("TurnLightControl.LeftTurnLightRequest", 0)]
```

### T2 Skip Conditions

- `novel_logic=True` handlers: T2 skips behavioral checks entirely. The handler is a stub (`pass`), so no behavioral verification is meaningful.
- PeriodicBlinkingOutput (P1): T2 verifies the state toggle (enable/disable blinking) but does NOT verify the periodic ticker behavior (that requires async time-based testing, which is T3 territory).

## T3: Composition Verifier

**Purpose**: Verify that the composed model (all handlers + state + periodic tasks + reset) has no systemic conflicts or lifecycle issues.

**How it works**: T3 operates on the complete IR + generated code together. It checks cross-handler consistency, lifecycle completeness, and pattern compatibility.

### T3 Checks

| # | Check Name | Description | Implementation |
|---|------------|-------------|----------------|
| 1 | `no_duplicate_handler_names` | No two handlers have the same name in the generated model | Compare all `HandlerIR.name` values for uniqueness |
| 2 | `no_duplicate_state_ownership` | No two handlers claim ownership of the same state variable | Compare all `StateIR.owner` fields for uniqueness |
| 3 | `no_pattern_conflicts` | No two handlers write to the same output signal with conflicting logic | Build signal-write map: `{output_signal: [handler_name, pattern]}` → check no signal is written by handlers with different patterns |
| 4 | `periodic_tasks_have_cleanup` | Every periodic task declares `cleanup=True` | Check all `PeriodicTaskIR.cleanup` values |
| 5 | `reset_covered_all_owned_states` | Reset handler resets all owned state variables | If `reset_handler` exists, check all `StateIR` with `reset_value` are in `ResetHandlerIR.states_to_reset` |
| 6 | `reset_covered_all_output_namespaces` | Reset handler calls `restbus.reset()` on all output namespaces | If `reset_handler` exists, check all output namespace names are in `ResetHandlerIR.namespaces_to_reset` |
| 7 | `input_namespace_not_output` | An input namespace is not also the output namespace for the same handler (unless role is "both") | Check `HandlerIR.input_namespace != HandlerIR.output_namespace` (or namespace role is "both") |
| 8 | `frame_filter_unique_per_namespace` | No duplicate FrameFilter on the same input namespace | Build map `{(namespace, frame_filter): [handler_name]}` → check no duplicates |
| 9 | `novel_logic_handlers_listed` | All novel_logic handlers are listed in IR and report | Check `BehavioralModelIR.novel_logic_handlers` matches handlers with `novel_logic=True` |
| 10 | `composed_model_has_no_invalid_lifecycle` | Model can be constructed and started without configuration errors | (Future: instantiate model with mock broker, check `__aenter__` succeeds) |

### T3 Conflict Resolution

When two handlers write to the same output signal:
- **Same pattern**: Both are `DirectSignalMapping` → warning only (multiple sources for same signal)
- **Different pattern**: One is `DirectSignalMapping`, other is `ToggleButtonState` → **FAIL** (conflicting logic)
- **One is `novel_logic`**: → warning (novel_logic handler may resolve conflict manually)

## Verification Report JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "VerificationReport",
  "type": "object",
  "required": ["status", "checks", "generated_files", "errors", "warnings"],
  "properties": {
    "status": {
      "type": "string",
      "enum": ["PASS", "FAIL"],
      "description": "Overall verification status. PASS only if all checks pass."
    },
    "checks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["layer", "name", "status", "message"],
        "properties": {
          "layer": {
            "type": "string",
            "enum": ["structural", "behavioral", "composition"],
            "description": "Verification layer that produced this check."
          },
          "name": {
            "type": "string",
            "description": "Check name (e.g., 'handler_async', 'direct_signal_mapping_output_correct')."
          },
          "status": {
            "type": "string",
            "enum": ["PASS", "FAIL", "SKIP"],
            "description": "PASS = check succeeded. FAIL = check failed. SKIP = check skipped (e.g., novel_logic handler)."
          },
          "message": {
            "type": "string",
            "description": "Human-readable message explaining the result. Empty string for PASS. Error detail for FAIL. Skip reason for SKIP."
          }
        }
      }
    },
    "generated_files": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of generated Python file paths that were verified."
    },
    "errors": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["layer", "check", "message"],
        "properties": {
          "layer": { "type": "string" },
          "check": { "type": "string" },
          "message": { "type": "string" }
        }
      },
      "description": "List of all FAIL results with details. Empty array if status is PASS."
    },
    "warnings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "handler", "message"],
        "properties": {
          "type": { "type": "string", "enum": ["novel_logic", "duplicate_signal_source", "other"] },
          "handler": { "type": "string" },
          "message": { "type": "string" }
        }
      },
      "description": "List of warnings that do not cause FAIL but should be reviewed. Includes novel_logic handlers."
    }
  }
}
```

### PASS/FAIL Semantics

| Overall Status | Condition |
|----------------|-----------|
| **PASS** | Every check has status `PASS` or `SKIP`. No `FAIL` results. Warnings may exist but do not block. |
| **FAIL** | Any check has status `FAIL`. The `errors` array contains all FAIL results. The pipeline stops at the layer where the first FAIL occurs. |

**SKIP semantics**: A check is `SKIP` when:
- The handler is marked `novel_logic=True` and the check is behavioral (T2)
- The check is pattern-specific and the handler uses a different pattern
- The handler has no state, and the check is state-related

**Warning semantics**: A warning is informational and does not affect the overall `status`. Common warnings:
- `novel_logic` handler requires manual implementation
- Two handlers write to the same output signal (same pattern)
- Reset handler not generated (no state to reset)

### Example Verification Report (PASS)

```json
{
  "status": "PASS",
  "checks": [
    {"layer": "structural", "name": "file_exists", "status": "PASS", "message": "generated/bcm/__main__.py found"},
    {"layer": "structural", "name": "syntax_valid", "status": "PASS", "message": "Python syntax valid"},
    {"layer": "structural", "name": "module_imports", "status": "PASS", "message": "All imports successful"},
    {"layer": "structural", "name": "handler_async", "status": "PASS", "message": "on_hazard_light is async def"},
    {"layer": "structural", "name": "handler_accepts_frame", "status": "PASS", "message": "on_hazard_light accepts frame: Frame"},
    {"layer": "structural", "name": "namespace_refs_exist", "status": "PASS", "message": "BCM-BodyCan0 and BCM-DriverCan0 found"},
    {"layer": "structural", "name": "output_has_restbus", "status": "PASS", "message": "BCM-BodyCan0 has restbus_configs"},
    {"layer": "structural", "name": "input_has_frame_filter", "status": "PASS", "message": "HazardLightButton FrameFilter found"},
    {"layer": "structural", "name": "restbus_update_signals_used", "status": "PASS", "message": "on_hazard_light calls restbus.update_signals"},
    {"layer": "behavioral", "name": "handler_callable_with_fake_frame", "status": "PASS", "message": "on_hazard_light called successfully"},
    {"layer": "behavioral", "name": "direct_signal_mapping_output_correct", "status": "PASS", "message": "Output values match input signal value"},
    {"layer": "composition", "name": "no_duplicate_handler_names", "status": "PASS", "message": "All handler names unique"},
    {"layer": "composition", "name": "no_duplicate_state_ownership", "status": "PASS", "message": "No shared state fields"},
    {"layer": "composition", "name": "no_pattern_conflicts", "status": "PASS", "message": "No conflicting output signals"}
  ],
  "generated_files": ["generated/bcm/__main__.py"],
  "errors": [],
  "warnings": []
}
```

### Example Verification Report (FAIL — T1)

```json
{
  "status": "FAIL",
  "checks": [
    {"layer": "structural", "name": "file_exists", "status": "PASS", "message": "generated/bcm/__main__.py found"},
    {"layer": "structural", "name": "syntax_valid", "status": "PASS", "message": "Python syntax valid"},
    {"layer": "structural", "name": "handler_async", "status": "FAIL", "message": "Handler 'on_hazard_light' is not async. Found: def on_hazard_light(self, frame)"}
  ],
  "generated_files": ["generated/bcm/__main__.py"],
  "errors": [
    {"layer": "structural", "check": "handler_async", "message": "Handler 'on_hazard_light' is not async. Found: def on_hazard_light(self, frame)"}
  ],
  "warnings": []
}
```

### Example Verification Report (PASS with novel_logic warning)

```json
{
  "status": "PASS",
  "checks": [
    {"layer": "structural", "name": "file_exists", "status": "PASS", "message": "generated/bcm/__main__.py found"},
    {"layer": "structural", "name": "handler_async", "status": "PASS", "message": "on_custom_logic is async def"},
    {"layer": "behavioral", "name": "handler_callable_with_fake_frame", "status": "SKIP", "message": "novel_logic handler: behavioral check skipped"},
    {"layer": "composition", "name": "no_pattern_conflicts", "status": "PASS", "message": "No conflicting output signals"}
  ],
  "generated_files": ["generated/bcm/__main__.py"],
  "errors": [],
  "warnings": [
    {"type": "novel_logic", "handler": "on_custom_logic", "message": "Handler requires manual implementation. Behavioral verification skipped."}
  ]
}
```
