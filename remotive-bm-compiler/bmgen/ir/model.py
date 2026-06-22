"""IR dataclass definitions for the Remotive Behavioral Model Compiler.

These dataclasses represent the typed Intermediate Representation that sits
between the YAML input spec and the deterministic compiler. The IR enforces
structural correctness (types, required fields) while validators enforce
semantic correctness (uniqueness, cross-references, invariants).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RestbusConfigIR:
    """Restbus configuration for an output CAN namespace.

    In Remotive Behavioral Models, output namespaces must have a RestbusConfig
    with a SenderFilter that identifies the ECU as the sender. This tells the
    broker which frames this ECU is responsible for producing.
    """
    sender_filter: str  # ECU name for SenderFilter (e.g., "BCM")


@dataclass
class NamespaceIR:
    """A namespace used by the behavioral model.

    Namespaces correspond to CAN bus interfaces that the ECU reads from (input)
    or writes to (output). Output namespaces require restbus configuration.

    Attributes:
        python_var_name: Derived snake_case Python variable name for use in
            generated code. E.g., "BCM-BodyCan0" → "body_can_0"
    """
    name: str
    type: str  # "can" | "lin" | "someip" (MVP: only "can")
    role: str  # "input" | "output" | "both"
    restbus: RestbusConfigIR | None = None
    client_id: int | None = None  # Future: SOME/IP client_id
    interface_name: str | None = None  # Future: LIN interface name
    python_var_name: str = ""

    def __post_init__(self):
        if not self.python_var_name:
            self.python_var_name = _derive_python_var_name(self.name)


@dataclass
class InputSignalIR:
    """An input signal reference within a handler.

    Attributes:
        python_var_name: Derived snake_case variable name for the signal value
            in generated code. E.g., "HazardLightButton.HazardLightButton" → "hazard_signal"
    """
    name: str  # Signal reference (e.g., "HazardLightButton.HazardLightButton")
    python_var_name: str = ""

    def __post_init__(self):
        if not self.python_var_name:
            self.python_var_name = _derive_signal_var_name(self.name)


@dataclass
class OutputSignalIR:
    """An output signal reference within a handler.

    Attributes:
        value_expr: Expression for the value to write. E.g., "hazard_signal" for
            DirectSignalMapping, or "1 if hazard_enabled else 0" for ToggleButtonState
    """
    name: str  # Signal reference (e.g., "TurnLightControl.RightTurnLightRequest")
    value_expr: str = ""  # Expression for value (derived by recipe)


@dataclass
class StateIR:
    """A state variable owned by a handler.

    State variables represent internal ECU state that persists between handler
    invocations. Each state must have exactly one owner handler.

    For toggle patterns: initial is the starting value, reset_value is what the
    state returns to on reboot/reset.
    """
    name: str  # State variable name (e.g., "hazard_enabled")
    type: str  # "bool" | "int" | "float" | "str"
    initial: Any  # Initial value (must match type)
    reset_value: Any  # Value on reset/reboot (must match type)
    owner: str  # Handler name that owns this state


@dataclass
class PeriodicTaskIR:
    """A periodic async task (e.g., blinking output).

    Periodic tasks use the Remotive `create_ticker` API to toggle signals at
    regular intervals. The cleanup flag ensures the ticker is cancelled when
    the handler exits or the model reboots.
    """
    interval_sec: float  # Blink interval in seconds
    blink_output_namespace: str  # Namespace for blink output signals
    blink_output_signals: list[str]  # Signals to toggle on/off
    cleanup: bool  # Must be True (ticker must be cancelled on exit)


@dataclass
class HandlerIR:
    """A handler within the behavioral model.

    Each handler corresponds to one input frame filter → one async method that
    processes the frame and produces output signals. The pattern field maps to
    a recipe that determines the handler's behavioral logic.

    Attributes:
        threshold: Optional float threshold for ThresholdMapping pattern.
            When set, the handler compares the input signal against this value
            and outputs 1 if input > threshold, else 0.
        operator: Optional comparison operator for ThresholdMapping. One of
            `>`, `>=`, `<`, `<=`, `==`, `!=`. Defaults to `>` (the original
            behavior) so existing specs without `operator:` render unchanged.
        true_when: Optional direction for ThresholdMapping. `above` (default)
            means TRUE (1) when the comparison holds; `below` means TRUE when
            the comparison does NOT hold (i.e. logical negation). This lets a
            rule like "child present when weight is LIGHT" be expressed as
            `operator: ">=", true_when: below` → `1 if not (weight >= 8) else 0`,
            without falling back to novel_logic.
    """
    name: str  # Handler method name (e.g., "on_hazard_light")
    pattern: str  # Recipe pattern name (e.g., "DirectSignalMapping")
    novel_logic: bool = False  # If true, generates stub handler
    input_namespace: str = ""  # Must reference existing NamespaceIR.name
    input_frame_filter: str = ""  # Frame name for FrameFilter
    input_signals: list[InputSignalIR] = field(default_factory=list)
    output_namespace: str = ""  # Must reference output NamespaceIR.name
    output_signals: list[OutputSignalIR] = field(default_factory=list)
    state: StateIR | None = None  # Optional state variable
    periodic_task: PeriodicTaskIR | None = None  # Optional periodic task
    threshold: float | None = None  # Optional threshold for ThresholdMapping
    operator: str | None = None  # Optional comparison operator (default ">")
    true_when: str | None = None  # Optional direction: "above" (default) | "below"


@dataclass
class ResetHandlerIR:
    """Reset/reboot handler that resets all owned states and output namespaces.

    Generated when any handler has a state with a reset_value, or when the
    YAML spec explicitly requests reset_handler: true.
    """
    states_to_reset: list[StateIR] = field(default_factory=list)
    namespaces_to_reset: list[str] = field(default_factory=list)  # Output namespace names


@dataclass
class WebsocketListenerIR:
    """A model-level websocket listener that bridges an external stream onto CAN.

    A websocket listener is NOT a handler. Handlers are triggered by incoming
    CAN frames (create_input_handler + FrameFilter); a websocket has no CAN
    frame, so it cannot be a handler. Instead, a listener is a long-running
    background asyncio task launched at model startup (inside the
    BehavioralModel context, before run_forever) and cancelled on exit/reboot.

    The listener reads JSON messages from `url`, extracts each `ws_key` from
    the payload, and publishes the value to the matching restbus signal on
    `output_namespace`. On disconnect/error it logs a warning and reconnects
    after `reconnect_delay_sec` seconds.

    Attributes:
        name: Unique listener identifier (used to derive generated method names).
        url: Websocket endpoint, must start with ws:// or wss://.
        output_namespace: Name of the CAN output namespace to publish onto.
            Must reference an existing NamespaceIR with role output/both + restbus.
        signal_map: List of (ws_key, restbus_signal) pairs mapping JSON payload
            keys to CAN restbus signals. At least one entry required.
        cleanup: Must be True — the background task must be cancelled on exit.
        reconnect_delay_sec: Backoff between reconnect attempts (default 2.0).
    """
    name: str
    url: str
    output_namespace: str
    signal_map: list[tuple[str, str]] = field(default_factory=list)
    cleanup: bool = True
    reconnect_delay_sec: float = 2.0


@dataclass
class BehavioralModelIR:
    """Top-level IR representing a complete behavioral model spec.

    This is the validated, typed representation that the compiler consumes.
    All invariants must be verified before passing this to the compiler.
    """
    name: str  # Model class name (e.g., "BCM")
    ecu_name: str  # ECU identifier (e.g., "BCM")
    namespaces: list[NamespaceIR] = field(default_factory=list)
    handlers: list[HandlerIR] = field(default_factory=list)
    reset_handler: ResetHandlerIR | None = None
    novel_logic_handlers: list[str] = field(default_factory=list)
    # Model-level websocket listeners (external ws → CAN restbus). Sibling to
    # handlers/reset_handler — NOT inside handlers[]. Defaults to [] so every
    # existing model that omits the websocket_listeners: key is unaffected.
    websocket_listeners: list[WebsocketListenerIR] = field(default_factory=list)


def _derive_python_var_name(namespace_name: str) -> str:
    """Convert a Remotive namespace name to a Python snake_case variable name.

    E.g., "BCM-BodyCan0" → "body_can_0"
         "BCM-DriverCan0" → "driver_can_0"

    The convention follows the reference examples where "BCM-BodyCan0" is
    accessed as `self.body_can_0` in Python code.
    """
    # Remove the ECU prefix (e.g., "BCM-") and convert to snake_case
    parts = namespace_name.split("-", 1)
    if len(parts) == 2:
        suffix = parts[1]
    else:
        suffix = parts[0]

    # Convert CamelCase/PascalCase to snake_case, handling trailing digits
    # E.g., "BodyCan0" → "body_can_0" (digit separated with underscore)
    result = []
    i = 0
    while i < len(suffix):
        char = suffix[i]
        if i > 0:
            prev_char = suffix[i - 1]
            # Insert underscore before uppercase letter that follows lowercase
            if char.isupper() and prev_char.islower():
                result.append("_")
            # Insert underscore between consecutive uppercase letters if next is lowercase
            # E.g., "BCR" in "BCRControl" → "bcr_control" (but "Can" → "can")
            elif char.isupper() and prev_char.isupper() and i + 1 < len(suffix) and suffix[i + 1].islower():
                result.append("_")
            # Insert underscore before digit that follows a letter
            elif char.isdigit() and prev_char.isalpha():
                result.append("_")
        result.append(char.lower())
        i += 1

    return "".join(result)


def _derive_signal_var_name(signal_ref: str) -> str:
    """Convert a Remotive signal reference to a Python snake_case variable name.

    E.g., "HazardLightButton.HazardLightButton" → "hazard_signal"
         "TurnStalk.TurnSignal" → "turn_signal"
         "BrakePedalPositionSensor.BrakePedalPosition" → "brake_signal"

    Uses the frame name (first part before '.') as the basis, since the
    signal name (second part) is often redundant with the frame name.
    """
    parts = signal_ref.split(".", 1)
    frame_name = parts[0]

    # Convert CamelCase to snake_case
    result = []
    for i, char in enumerate(frame_name):
        if char.isupper() and i > 0:
            prev_lower = frame_name[i - 1].islower()
            next_lower = i + 1 < len(frame_name) and frame_name[i + 1].islower()
            if prev_lower or next_lower:
                result.append("_")
        result.append(char.lower())

    var_name = "".join(result)

    # Add "_signal" suffix for clarity
    if not var_name.endswith("_signal"):
        var_name += "_signal"

    return var_name
