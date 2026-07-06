# IR Schema — Remotive Behavioral Model Compiler

> **Schema version**: `service_oriented` — namespace_types map + multi-output handlers
> **Last updated**: 2026-07-06

## Why YAML Alone Is Not Enough

YAML is a **serialization format** — it represents data as key-value pairs and lists. It has no concept of:
- **Type enforcement**: A YAML string `"BCM"` could be a namespace name, an ECU name, or a signal name — YAML cannot distinguish
- **Invariant validation**: YAML cannot enforce "namespace names must be unique" or "output namespace must have restbus config"
- **Cross-reference resolution**: YAML cannot verify that `"SEAT-CpdCan0"` referenced in a handler actually exists in the `namespace_types:` map
- **Behavioral semantics**: YAML cannot express "this handler reads one signal and writes the same value to multiple outputs" vs "this handler toggles a boolean state"

The **typed IR** layer provides:
1. **Structural typing**: Each field has a Python type (str, list, enum, optional). Invalid types are caught at IR construction time, not at code generation time.
2. **Invariant enforcement**: The validators module checks 16 semantic rules. Violations are reported before any code is generated.
3. **Recipe matching**: The IR `pattern` field maps to a recipe class, and the recipe validates that the handler IR has the correct structure for that pattern.
4. **Deterministic compilation**: With a validated IR, the compiler always produces the same output.

## Schema Evolution: `namespaces:` → `namespace_types:`

The `service_oriented` branch replaces the verbose `namespaces:` list block with a flat `namespace_types:` map. Here's why:

### Before (old schema)
```yaml
namespaces:
  - name: SEAT-CpdCan0
    type: can
    role: both          # derivable from handler refs
    restbus:             # derivable — any output/both namespace needs this
      sender_filter: SEAT  # always = ecu_name
  - name: SEAT-CpdCan1
    type: can
    role: input         # derivable — only used as input by handlers
```

**Problems with the old schema**:
- 4-6 lines per namespace, most of which are derivable
- `role` can be wrong (mismatch between declaration and actual usage)
- `restbus.sender_filter` was always `ecu_name` — the template [hardcodes `SenderFilter(ecu_name="{{ ecu_name }}")`](../remotive-bm-compiler/bmgen/compiler/templates/main.py.j2#L87)
- No typo protection — a handler ref to a namespace not in the list was caught, but a namespace declared and never referenced was silently accepted (drift bug)

### After (new schema)
```yaml
namespace_types:
  SEAT-CpdCan0: can
  SEAT-CpdCan1: can
```

**What changed**:
- **Type only** — the `type` field is the only value the user must declare (future: `lin`, `someip`)
- **Role inferred** — from handler input/output references (`"both"`, `"input"`, `"output"`)
- **Restbus auto-created** — any namespace with role `"output"` or `"both"` gets `RestbusConfigIR(sender_filter=ecu_name)`
- **Strict-required** — every name referenced in handlers/ws must appear in `namespace_types:` (Invariant 14, error)
- **Orphan warning** — every name declared but never referenced produces a warning (Invariant 16)

## YAML Input Schema

### Top-Level Structure

```yaml
model:
  name: <string>            # Required. Model class name (e.g., "SeatECU")
  ecu_name: <string>        # Required. ECU identifier (e.g., "SEAT")

namespace_types:            # Required. Flat map of name → type. Replaces the old
                            # `namespaces:` list block. Role + restbus are inferred.
  <namespace_name>: <type>  # type: "can" (MVP). Future: "lin", "someip"

handlers:
  - name: <string>          # Required. Handler method name (e.g., "on_seat_occupancy")
    pattern: <string>       # Required. Recipe pattern name
    novel_logic: <bool>     # Optional. Default false. If true, generates stub.
    input:
      namespace: <string>   # Required. Input namespace (must be in namespace_types)
      frame_filter: <string> # Required. Frame name for FrameFilter
      signal: <string>      # Required (single-signal). Signal reference
      signals:               # Alternative (multi-signal). List of signal refs
        - <string>
    output:                 # LIST of {namespace, signals} groups (new in service_oriented)
      - namespace: <string> # Required. Output namespace (must be in namespace_types)
        signals:            # Required. List of output signal names
          - <string>
    # Single-output back-compat: a dict {namespace, signals} is still accepted
    # and is normalized to a one-element list by the builder.
    state:                   # Optional. Required for ToggleButtonState, PeriodicBlinkingOutput
      name: <string>
      type: <enum>           # "bool" | "int" | "float" | "str"
      initial: <value>
      reset_value: <value>
      owner: <string>
    periodic_task:           # Optional. Required for PeriodicBlinkingOutput
      interval_sec: <float>
      blink_output:
        namespace: <string>
        signals:
          - <string>
      cleanup: <bool>
    threshold: <float>       # Optional. Required for ThresholdMapping pattern
    operator: <string>       # Optional. One of >, >=, <, <=, ==, !=. Default: >
    true_when: <string>      # Optional. "above" (default) or "below"

websocket_listeners:        # Optional. Model-level (sibling to handlers, not inside)
  - name: <string>          # Required. Unique listener identifier
    url: <string>           # Required. Must start with ws:// or wss://
    output_namespace: <string> # Required. CAN namespace to publish onto
    signal_map:             # Required. At least one entry
      - ws_key: <string>    # JSON payload key to extract
        signal: <string>    # Restbus signal to publish value to
    cleanup: <bool>         # Required. Must be true (task cancelled on exit/reboot)
    reconnect_delay_sec: <float> # Optional. Default 2.0s

reset_handler: <bool>        # Optional. Default false.
```

### Example: Multi-Output (the `new_schema.yaml` target)

```yaml
model:
  name: SeatECU
  ecu_name: SEAT

namespace_types:
  SEAT-CpdCan0: can
  SEAT-CpdCan1: can

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
        signals: [SeatInput.SeatOccupied]
      - namespace: SEAT-CpdCan1
        signals: [SeatInput.SeatOccupiedBackup]
```

This spec produces **two** `restbus.update_signals()` calls in `on_seat_occupancy` — one per output group, in declaration order, with the same computed threshold value `1 if not (seat_weight_sensor_signal >= 8) else 0` fanned out to both namespaces.

### Example: Single-Output (migrated child_detection ECUs)

```yaml
model:
  name: CockpitHMIECU
  ecu_name: COCKPIT

namespace_types:
  COCKPIT-CpdCan0: can

handlers:
  - name: on_child_alert
    pattern: DirectSignalMapping
    input:
      namespace: COCKPIT-CpdCan0
      frame_filter: ChildAlert
      signal: ChildAlert.ChildAlertActive
    output:
      - namespace: COCKPIT-CpdCan0
        signals:
          - HmiChildWarning.ChildAlertActive
```

Single-output handlers with a one-element `output:` list generate **byte-identical** Python to the old schema. The template's `{% if output_groups|length > 1 %}` branch takes the else-path, which matches the pre-refactor rendering exactly.

### Example: Websocket-Only ECU (no handlers)

```yaml
model:
  name: DriverMonitoringECU
  ecu_name: DMS

namespace_types:
  DMS-CpdCan0: can

websocket_listeners:
  - name: camera_child_detection
    url: ws://localhost:1122
    output_namespace: DMS-CpdCan0
    signal_map:
      - ws_key: ChildDetected
        signal: CameraInput.ChildDetectedByCamera
    cleanup: true
    reconnect_delay_sec: 2.0

handlers: []
```

The builder infers `DMS-CpdCan0` as role `"output"` (referenced only by the websocket listener's `output_namespace`) and auto-creates its restbus. The generated code runs a background asyncio task that reads JSON from the websocket and publishes each `ws_key` value to the matching restbus signal.

### Example: WeightedLogOdds (CAD — `inc_schema/SWC_CAD_logic.yaml`)

```yaml
handlers:
  - name: CAD_logic
    pattern:
      - name: WeightedLogOdds
        weights:
          SeatInput.SeatOccupied: 1.0
          CameraInput.ChildDetectedByCamera: 1.0
          AirbagStatusReport.AirbagStatus: 2.0
        threshold: 3.0
    input:
      - namespace: CENTRAL-CpdCan0
        signal: SeatInput.SeatOccupied
      - namespace: DMS-CpdCan0
        signal: CameraInput.ChildDetectedByCamera
      - namespace: AIRBAG-CpdCan0
        signal: AirbagStatusReport.AirbagStatus
    output:
      - namespace: CENTRAL-CpdCan0
        signals: [ChildAlert.ChildAlertActive]
```

**Observed codegen behavior** (`handler_weighted.py.j2`):

- Per-input **latch** fields on the model dataclass (`self._*_latched`) — updated when that signal appears on an incoming frame.
- One handler method; **multiple** `create_input_handler` registrations (one per unique namespace/frame).
- `sum_expr` uses `self.<latched_var>` in the weighted sum; compare to `threshold` for output 0/1.
- User must **not** declare top-level `state:` for this pattern (recipe-managed latches).

### Example: ECU composition (`inc_schema/centralHPC.yaml`)

```yaml
ecu:
  name: CentralHPC
  broker_name: CENTRAL

namespace_types:
  CENTRAL-CpdCan0: can
  SEAT-CpdCan0: can      # fan-in read (cross-ECU)
  DMS-CpdCan0: can
  AIRBAG-CpdCan0: can

software_components:
  - ./SWC_CAD_logic.yaml
  - ./SWC_evaluate_decision.yaml
```

The builder merges SWC handler lists into one `BehavioralModelIR` per ECU entry file.

## Typed IR Definitions

### `BehavioralModelIR`

```python
@dataclass
class BehavioralModelIR:
    name: str                              # Model class name (e.g., "SeatECU")
    ecu_name: str                          # ECU identifier (e.g., "SEAT")
    namespaces: list[NamespaceIR]          # Inferred from handler/ws refs + namespace_types map
    handlers: list[HandlerIR]              # All handlers for this model
    reset_handler: ResetHandlerIR | None   # Optional on_reboot handler
    novel_logic_handlers: list[str]        # Handler names marked novel_logic
    websocket_listeners: list[WebsocketListenerIR]  # Model-level ws → CAN bridges
```

### `NamespaceIR`

```python
@dataclass
class NamespaceIR:
    name: str                              # e.g., "SEAT-CpdCan0"
    type: str                              # from namespace_types map. MVP: "can"
    role: str                              # inferred: "input" | "output" | "both"
    restbus: RestbusConfigIR | None        # auto-created if role is output/both
    client_id: int | None                  # Future: SOME/IP
    interface_name: str | None             # Future: LIN
    python_var_name: str                   # Derived: "SEAT-CpdCan0" → "cpd_can_0"

@dataclass
class RestbusConfigIR:
    sender_filter: str                     # Always = ecu_name
```

### `OutputGroupIR` — NEW in service_oriented

```python
@dataclass
class OutputGroupIR:
    """One output binding: write the recipe's value_expr to these signals
    on this namespace.

    A handler may write to one or more output namespaces. Each OutputGroupIR
    binds a (namespace, signals) pair. The recipe's output_value_expr() returns
    a single expression that is fanned out to every signal across every group.
    """
    namespace: str
    signals: list[OutputSignalIR] = field(default_factory=list)
```

### `HandlerIR`

```python
@dataclass
class HandlerIR:
    name: str                              # Handler method name
    pattern: str                           # Recipe pattern name
    novel_logic: bool = False              # Stub handler escape hatch
    input_namespace: str = ""              # Input namespace (must exist)
    input_frame_filter: str = ""           # Frame name for FrameFilter
    input_signals: list[InputSignalIR]     # Input signal references
    output_groups: list[OutputGroupIR]     # Output (namespace, signals) groups
                                           #   Replaces old: output_namespace + output_signals
    state: StateIR | None = None
    periodic_task: PeriodicTaskIR | None = None
    threshold: float | None = None         # For ThresholdMapping
    operator: str | None = None            # Comparison operator (default ">")
    true_when: str | None = None           # "above" (default) | "below"
```

### `WebsocketListenerIR` — NEW in service_oriented

```python
@dataclass
class WebsocketListenerIR:
    """Model-level websocket listener bridging external stream onto CAN.

    NOT a handler — handlers are triggered by CAN frames. A websocket has no
    CAN frame, so it runs as a background asyncio task for the ECU's lifetime.
    """
    name: str                              # Unique listener identifier
    url: str                               # ws:// or wss:// endpoint
    output_namespace: str                  # CAN output namespace to publish onto
    signal_map: list[tuple[str, str]]      # (ws_key, restbus_signal) pairs
    cleanup: bool = True                   # Must be True
    reconnect_delay_sec: float = 2.0
```

### Other IR types (unchanged)

```python
@dataclass
class InputSignalIR:
    name: str                              # e.g., "SeatWeightSensor.WeightKg"
    python_var_name: str                   # Derived: "seat_weight_sensor_signal"

@dataclass
class OutputSignalIR:
    name: str                              # e.g., "SeatInput.SeatOccupied"
    value_expr: str = ""                   # Stamped by recipe.output_value_expr()

@dataclass
class StateIR:
    name: str
    type: str                              # "bool" | "int" | "float" | "str"
    initial: Any
    reset_value: Any
    owner: str

@dataclass
class PeriodicTaskIR:
    interval_sec: float
    blink_output_namespace: str
    blink_output_signals: list[str]
    cleanup: bool

@dataclass
class ResetHandlerIR:
    states_to_reset: list[StateIR]
    namespaces_to_reset: list[str]
```

## Validation Rules

### IR Invariants (checked by `validate(ir)`)

| # | Invariant | Description | Changed in service_oriented? |
|---|-----------|-------------|------|
| 1 | `namespace_names_unique` | All `NamespaceIR.name` values must be unique | No |
| 2 | `handler_names_unique` | All `HandlerIR.name` values must be unique | No |
| 3 | `handler_input_namespace_exists` | Handler's `input_namespace` must match a `NamespaceIR.name` | No |
| 4 | `handler_output_namespace_exists` | Every `output_group.namespace` must match a `NamespaceIR.name` | **Yes** — iterates `output_groups` |
| 5 | `output_namespace_has_restbus` | Every output namespace (from handler output_groups + ws output_namespace) must have role output/both + restbus | **Yes** — collects from groups + ws |
| 6 | `state_single_owner` | Each state must have exactly one owner | No |
| 7 | `periodic_task_has_cleanup` | Periodic tasks must declare `cleanup=True` | No |
| 8 | `resettable_state_has_reset_value` | Toggle/blink states must have `reset_value` | No |
| 9 | `unknown_pattern_fails_early` | Unknown pattern must be in registry or marked `novel_logic=True` | No (but registry is single source of truth) |
| 10 | `novel_logic_handlers_listed` | novel_logic handlers must be in `BehavioralModelIR.novel_logic_handlers` | No |
| 11 | `threshold_mapping_has_threshold` | ThresholdMapping requires `threshold` field | **New** (P1) |
| 12 | `websocket_listener_invalid` | WS listener: name unique, url valid, output_namespace exists+has restbus, signal_map non-empty, cleanup=True | **New** (P1) |
| 13 | `threshold_mapping_invalid_operator` / `threshold_mapping_invalid_true_when` | Operator must be in `{>, >=, <, <=, ==, !=}`, true_when in `{above, below}` | **New** (P1) |

### Namespace Types Schema Rules (checked by `validate_namespace_types(spec, ir)`)

These are **separate** from `validate(ir)` because they need the raw `spec` dict to read `namespace_types:` and check for the deprecated `namespaces:` block:

| # | Invariant | Severity | Description |
|---|-----------|----------|-------------|
| 14 | `namespace_type_required_for_referenced` | error | Every name in handler input_namespace / output_group.namespace / ws.output_namespace must be in `namespace_types:`. Skipped when deprecated `namespaces:` block is present (migration window). |
| 15 | `namespace_type_unknown` | error | Every key's value in `namespace_types:` must be in `{"can"}` (closed set). |
| 16 | `namespace_type_orphan` | warning | Every key in `namespace_types:` with zero refs produces a warning. Does NOT block the build. |

**Validation order**: `validate_namespace_types(spec, ir)` → `validate(ir)` → combine violations → check `has_errors()`. This means rules 14/15/16 fire alongside rules 1-13 in the same error report.

### Recipe-Specific Validation

| Pattern | Required Fields | Constraints |
|---------|----------------|-------------|
| `DirectSignalMapping` | 1 input signal, ≥1 output groups, no state | Reads signal, forwards value to outputs |
| `ToggleButtonState` | 1 input signal, ≥1 output groups, state (bool) | Rising-edge toggle, writes 1/0 |
| `PeriodicBlinkingOutput` | 1 input signal, state (bool), periodic_task (cleanup=True) | Enables/disables async ticker |
| `ThresholdMapping` | 1 input signal, threshold (float), operator (optional, default `>`), true_when (optional, default `above`) | Compares analog input against threshold, outputs boolean 0/1 |
| `LogicAnd` / `LogicOr` / `LogicXor` | 2 input signals, ≥1 output groups, no state | Bitwise boolean gate, writes 1/0 |
| `LogicNot` | 1 input signal, ≥1 output groups, no state | Bitwise NOT, writes 1/0 |
| `WebsocketBridge` | Validates `WebsocketListenerIR` (not `HandlerIR`) | ws_url format, signal_map non-empty, cleanup=True |
