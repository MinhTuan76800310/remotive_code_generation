# IR Schema — Remotive Behavioral Model Compiler

## Why YAML Alone Is Not Enough

YAML is a **serialization format** — it represents data as key-value pairs and lists. It has no concept of:
- **Type enforcement**: A YAML string `"BCM"` could be a namespace name, an ECU name, or a signal name — YAML cannot distinguish
- **Invariant validation**: YAML cannot enforce "namespace names must be unique" or "output namespace must have restbus config"
- **Cross-reference resolution**: YAML cannot verify that `"BCM-DriverCan0"` referenced in a handler actually exists in the namespaces list
- **Behavioral semantics**: YAML cannot express "this handler reads one signal and writes the same value to multiple outputs" vs "this handler toggles a boolean state"

The **typed IR** layer provides:
1. **Structural typing**: Each field has a Python type (str, list, enum, optional). Invalid types are caught at IR construction time, not at code generation time.
2. **Invariant enforcement**: The validators module checks all semantic rules (uniqueness, existence, consistency). Violations are reported before any code is generated.
3. **Recipe matching**: The IR `pattern` field maps to a recipe class, and the recipe validates that the handler IR has the correct structure for that pattern. This catch occurs before template rendering.
4. **Deterministic compilation**: With a validated IR, the compiler always produces the same output. There is no ambiguity about what code to generate.

**In short**: YAML is the *user-facing* format (easy to write, easy to read). The typed IR is the *machine-facing* format (enforces correctness, enables deterministic compilation). The gap between them is closed by the `parser → builder → validator` pipeline.

## YAML Input Schema

### Top-Level Structure

```yaml
model:
  name: <string>            # Required. Model class name (e.g., "BCM")
  ecu_name: <string>        # Required. ECU identifier (e.g., "BCM")

namespaces:
  - name: <string>          # Required. Namespace identifier (e.g., "BCM-BodyCan0")
    type: <enum>            # Required. "can" | "lin" | "someip" (MVP: only "can")
    role: <enum>            # Required. "input" | "output" | "both"
    restbus:                 # Required if role is "output" or "both"
      sender_filter: <string>  # Required. ECU name for SenderFilter (e.g., "BCM")
    client_id: <int>        # Optional. SOME/IP client_id (future: someip type)
    interface_name: <string> # Optional. LIN interface name (future: lin type)

handlers:
  - name: <string>          # Required. Handler method name (e.g., "on_hazard_light")
    pattern: <string>       # Required. Recipe pattern name (e.g., "DirectSignalMapping")
    novel_logic: <bool>     # Optional. Default false. If true, generates stub handler.
    input:
      namespace: <string>   # Required. Must reference a namespace from the namespaces list
      frame_filter: <string> # Required. Frame name for FrameFilter (e.g., "HazardLightButton")
      signal: <string>      # Required. Signal reference (e.g., "HazardLightButton.HazardLightButton")
    output:
      namespace: <string>   # Required. Must reference an output namespace with restbus
      signals:              # Required. List of output signal names
        - <string>
    state:                   # Optional. Required for ToggleButtonState and PeriodicBlinkingOutput
      name: <string>        # Required. State variable name (e.g., "hazard_enabled")
      type: <enum>          # Required. "bool" | "int" | "float" | "str"
      initial: <value>      # Required. Initial value matching type
      reset_value: <value>  # Required if state is used in toggle or blink. Value on reset/reboot.
      owner: <string>       # Required. Handler name that owns this state (must match handler name)
    periodic_task:           # Optional. Required for PeriodicBlinkingOutput
      interval_sec: <float>  # Required. Blink interval in seconds (e.g., 1.0)
      blink_output:          # Required. Signal(s) to toggle on/off
        namespace: <string>
        signals:
          - <string>
      cleanup: <bool>       # Required. Must be true for periodic tasks (cancel ticker on exit)

reset_handler: <bool>        # Optional. Default false. If true, generate on_reboot handler.
                            # Auto-set to true if any handler has state with reset_value.
```

### Example: `bcm_direct.yaml`

```yaml
model:
  name: BCM
  ecu_name: BCM

namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
  - name: BCM-DriverCan0
    type: can
    role: input

handlers:
  - name: on_hazard_light
    pattern: DirectSignalMapping
    input:
      namespace: BCM-DriverCan0
      frame_filter: HazardLightButton
      signal: HazardLightButton.HazardLightButton
    output:
      namespace: BCM-BodyCan0
      signals:
        - TurnLightControl.RightTurnLightRequest
        - TurnLightControl.LeftTurnLightRequest
```

This spec generates the exact same code as the `getting_started/models/bcm/__main__.py` reference example.

### Example: `bcm_toggle.yaml`

```yaml
model:
  name: BCM
  ecu_name: BCM

namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
  - name: BCM-DriverCan0
    type: can
    role: input

handlers:
  - name: on_hazard_button
    pattern: ToggleButtonState
    input:
      namespace: BCM-DriverCan0
      frame_filter: HazardLightButton
      signal: HazardLightButton.HazardLightButton
    output:
      namespace: BCM-BodyCan0
      signals:
        - TurnLightControl.RightTurnLightRequest
        - TurnLightControl.LeftTurnLightRequest
    state:
      name: hazard_enabled
      type: bool
      initial: false
      reset_value: false
      owner: on_hazard_button

reset_handler: true
```

This spec generates a BCM model with a toggle handler: pressing once → hazard_enabled=True → both lights ON; pressing again → hazard_enabled=False → both lights OFF. The `on_reboot` handler resets `hazard_enabled` to `false` and calls `body_can_0.restbus.reset()`.

### Example: `bcm_blinking.yaml` (MVP+)

```yaml
model:
  name: BCM
  ecu_name: BCM

namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
  - name: BCM-DriverCan0
    type: can
    role: input

handlers:
  - name: on_hazard_light
    pattern: DirectSignalMapping
    input:
      namespace: BCM-DriverCan0
      frame_filter: HazardLightButton
      signal: HazardLightButton.HazardLightButton
    output:
      namespace: BCM-BodyCan0
      signals:
        - TurnLightControl.RightTurnLightRequest
        - TurnLightControl.LeftTurnLightRequest

  - name: on_turn_stalk
    pattern: PeriodicBlinkingOutput
    input:
      namespace: BCM-DriverCan0
      frame_filter: TurnStalk
      signal: TurnStalk.TurnSignal
    output:
      namespace: BCM-BodyCan0
      signals:
        - TurnLightControl.LeftTurnLightRequest
    state:
      name: blink_enabled
      type: bool
      initial: false
      reset_value: false
      owner: on_turn_stalk
    periodic_task:
      interval_sec: 1.0
      blink_output:
        namespace: BCM-BodyCan0
        signals:
          - TurnLightControl.LeftTurnLightRequest
      cleanup: true

reset_handler: true
```

## Typed IR Definitions

### `BehavioralModelIR`

```python
@dataclass
class BehavioralModelIR:
    name: str                              # Model class name (e.g., "BCM")
    ecu_name: str                          # ECU identifier (e.g., "BCM")
    namespaces: list[NamespaceIR]          # All namespaces used by this model
    handlers: list[HandlerIR]              # All handlers for this model
    reset_handler: ResetHandlerIR | None   # Optional on_reboot handler
    novel_logic_handlers: list[str]        # Handler names marked novel_logic
```

### `NamespaceIR`

```python
@dataclass
class NamespaceIR:
    name: str                              # Namespace identifier (e.g., "BCM-BodyCan0")
    type: str                              # "can" | "lin" | "someip" (MVP: "can" only)
    role: str                              # "input" | "output" | "both"
    restbus: RestbusConfigIR | None        # Required if role is output/both
    client_id: int | None                  # Future: SOME/IP client_id
    interface_name: str | None             # Future: LIN interface name
    python_var_name: str                   # Derived: snake_case Python variable name
                                        #   "BCM-BodyCan0" → "body_can_0"

@dataclass
class RestbusConfigIR:
    sender_filter: str                     # ECU name for SenderFilter (e.g., "BCM")
```

### `HandlerIR`

```python
@dataclass
class HandlerIR:
    name: str                              # Handler method name (e.g., "on_hazard_light")
    pattern: str                           # Recipe pattern name (e.g., "DirectSignalMapping")
    novel_logic: bool                      # If true, generates stub handler
    input_namespace: str                   # Must reference existing NamespaceIR.name
    input_frame_filter: str                # Frame name for FrameFilter
    input_signals: list[InputSignalIR]     # Input signal references
    output_namespace: str                  # Must reference output NamespaceIR.name
    output_signals: list[OutputSignalIR]   # Output signal references
    state: StateIR | None                  # Optional state variable
    periodic_task: PeriodicTaskIR | None   # Optional periodic task
    recipe: RecipeIR | None                # Resolved recipe (set by registry lookup)
```

### `InputSignalIR`

```python
@dataclass
class InputSignalIR:
    name: str                              # Signal reference (e.g., "HazardLightButton.HazardLightButton")
    python_var_name: str                   # Derived: snake_case signal name
                                        #   "HazardLightButton.HazardLightButton" → "hazard_signal"
```

### `OutputSignalIR`

```python
@dataclass
class OutputSignalIR:
    name: str                              # Signal reference (e.g., "TurnLightControl.RightTurnLightRequest")
    value_expr: str                        # Expression for value (e.g., "hazard_signal" or "1 if hazard_enabled else 0")
```

### `StateIR`

```python
@dataclass
class StateIR:
    name: str                              # State variable name (e.g., "hazard_enabled")
    type: str                              # "bool" | "int" | "float" | "str"
    initial: Any                           # Initial value (must match type)
    reset_value: Any                       # Value on reset/reboot (must match type)
    owner: str                             # Handler name that owns this state
```

### `RecipeIR`

```python
@dataclass
class RecipeIR:
    pattern_name: str                      # Pattern name (e.g., "DirectSignalMapping")
    recipe_class: str                      # Python class name in recipes/ module
    required_input_count: int              # Minimum input signals required
    required_output_count: int             # Minimum output signals required
    requires_state: bool                   # Whether this recipe needs a state variable
    requires_periodic: bool                # Whether this recipe needs a periodic task
```

### `PeriodicTaskIR`

```python
@dataclass
class PeriodicTaskIR:
    interval_sec: float                    # Blink interval in seconds
    blink_output_namespace: str            # Namespace for blink output signals
    blink_output_signals: list[str]        # Signals to toggle on/off
    cleanup: bool                          # Must be True (ticker must be cancelled on exit)
```

### `ResetHandlerIR`

```python
@dataclass
class ResetHandlerIR:
    states_to_reset: list[StateIR]         # All owned states to reset
    namespaces_to_reset: list[str]         # All output namespaces to call restbus.reset() on
```

### `VerifierRuleIR`

```python
@dataclass
class VerifierRuleIR:
    layer: str                             # "structural" | "behavioral" | "composition"
    name: str                              # Check name (e.g., "handler_async")
    description: str                       # What this check verifies
    applies_to_patterns: list[str]         # Which patterns this check applies to (or ["*"] for all)
    severity: str                          # "error" | "warning"
```

## Validation Rules

### IR Invariants (checked by `validators.py`)

| # | Invariant | Description | Failure Mode |
|---|-----------|-------------|--------------|
| 1 | `namespace_names_unique` | All `NamespaceIR.name` values must be unique | Duplicate namespace name → violation |
| 2 | `handler_names_unique` | All `HandlerIR.name` values must be unique | Duplicate handler name → violation |
| 3 | `handler_input_namespace_exists` | `HandlerIR.input_namespace` must match some `NamespaceIR.name` | Non-existent namespace → violation |
| 4 | `handler_output_namespace_exists` | `HandlerIR.output_namespace` must match some `NamespaceIR.name` | Non-existent namespace → violation |
| 5 | `output_namespace_has_restbus` | Output namespace must have `role: output` and `restbus` config | Missing restbus → violation |
| 6 | `state_single_owner` | Each `StateIR.name` must have exactly one `owner` | Multiple owners → violation |
| 7 | `periodic_task_has_cleanup` | `PeriodicTaskIR.cleanup` must be `True` | Missing cleanup → violation |
| 8 | `resettable_state_has_reset_value` | If `StateIR` is used in toggle/blink pattern, `reset_value` must be set | Missing reset_value → violation |
| 9 | `unknown_pattern_fails_early` | `HandlerIR.pattern` must be in recipe registry or `novel_logic=True` | Unknown pattern without novel_logic → violation |
| 10 | `unsupported_logic_marked_novel` | Logic that cannot be compiled deterministically must be `novel_logic=True` | Will be checked per-recipe |

### Recipe-Specific Validation (checked by `recipe.validate(handler_ir)`)

| Pattern | Required Fields | Constraints |
|---------|----------------|-------------|
| `DirectSignalMapping` | `input_signals` (exactly 1), `output_signals` (≥1), no `state` | Reads one signal, forwards same value to outputs |
| `ToggleButtonState` | `input_signals` (exactly 1), `output_signals` (≥1), `state` (bool type) | Reads signal, toggles boolean, writes 1/0 |
| `PeriodicBlinkingOutput` | `input_signals` (exactly 1), `state` (bool), `periodic_task` (cleanup=True) | Enables/disables blinking, periodic ticker |

## External Source Assumptions

The following must be verified from the Remotive topology examples repository (https://github.com/remotivelabs/remotivelabs-topology-examples):

1. **`Frame` class API**: The `frame.signals` dict access pattern (`frame.signals["Frame.Signal"]`) is assumed to return a numeric value (float/int). The actual type should be verified from `remotivelabs.broker` source.

2. **`restbus.update_signals` signature**: Assumed to accept tuples of `(signal_name: str, value: float/int)` via `*args`. The actual signature should be verified.

3. **`CanNamespace` constructor**: Assumed to accept `(name: str, broker_client: BrokerClient, restbus_configs: list[RestbusConfig])`. The `restbus_configs` is optional for input-only namespaces. Should be verified.

4. **`RestbusConfig` constructor**: Assumed to accept `(filters: list[Filter], delay_multiplier: float)` where `delay_multiplier` comes from `avp.delay_multiplier`. Should be verified.

5. **`BehavioralModelArgs` API**: Assumed to have `.url`, `.auth`, `.delay_multiplier`, `.loglevel` attributes. Should be verified.

6. **`BehavioralModel` constructor**: Assumed to accept `(ecu_name: str, namespaces: list, broker_client: BrokerClient, input_handlers: list, control_handlers: list)` and support `async with` + `run_forever()`. Should be verified.

7. **`BrokerClient` lifecycle**: Assumed to support `async with BrokerClient(url, auth)` context manager pattern. Should be verified.

8. **`create_ticker` API** (for PeriodicBlinkingOutput): Assumed to be `from remotivelabs.topology.time.async_ticker import create_ticker` with signature `create_ticker(on_tick=async_func, interval_in_sec=float)` returning an `asyncio.Task`. Should be verified.

9. **`RebootRequest` handling**: Assumed to be `from remotivelabs.topology.behavioral_model import RebootRequest` with `type` attribute, and `ControlRequest`/`ControlResponse` from `remotivelabs.topology.control`. Should be verified.

10. **`restbus.reset()`**: Assumed to be `await namespace.restbus.reset()` for resetting all output signals. Should be verified.
