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
class OutputGroupIR:
    """One output binding: write the recipe's value_expr to these signals on this namespace.

    A handler may write to one or more output namespaces. Each OutputGroupIR
    binds a (namespace, signals) pair. The recipe's output_value_expr() returns
    a single expression that is fanned out to every signal across every group.

    Example (ThresholdMapping with two outputs):
        handler.output_groups = [
            OutputGroupIR(namespace="SEAT-CpdCan0", signals=[
                OutputSignalIR(name="SeatInput.SeatOccupied"),
            ]),
            OutputGroupIR(namespace="SEAT-CpdCan1", signals=[
                OutputSignalIR(name="SeatInput.SeatOccupiedBackup"),
            ]),
        ]

    This produces two update_signals() calls in the generated Python, one per
    group. The validator enforces that every OutputGroupIR.namespace resolves
    to an inferred NamespaceIR.
    """
    namespace: str
    signals: list[OutputSignalIR] = field(default_factory=list)


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
class WeightedInputIR:
    """One input of a WeightedLogOdds (CAD-style) recipe — a (namespace, signal, weight) triple.

    Unlike `InputSignalIR` (which is single-frame because handlers fire on one
    CAN frame), WeightedLogOdds may fan-in signals from MULTIPLE namespaces
    (e.g. SEAT-CpdCan0 + DMS-CpdCan0 + AIRBAG-CpdCan0 in the child-detection
    ECU). Each input must therefore carry its own namespace.

    Attributes:
        namespace: Source CAN namespace name (must exist in ir.namespaces).
        signal: Signal reference "Frame.Signal" within that namespace.
        weight: Floating-point coefficient applied to bool(signal) before summing.
        python_var_name: Derived snake_case local variable name in the generated
            handler. Defaults from `signal`, then disambiguated by the builder
            across siblings (see HandlerIR.builder helper).
        frame_filter: Resolved frame name — either explicit `frame_filter:` from
            the YAML, or inferred from `signal.split(".", 1)[0]`. The handler
            creates one FrameFilter per UNIQUE frame across the weighted inputs.
    """
    namespace: str
    signal: str
    weight: float
    python_var_name: str = ""
    frame_filter: str = ""

    def __post_init__(self):
        if not self.python_var_name:
            self.python_var_name = _derive_signal_var_name(self.signal)
        if not self.frame_filter:
            # Default inference: frame name = substring of signal before first '.'.
            # This mirrors the project convention — every signal in inc_schema/
            # is named "<FrameName>.<SignalName>", so the frame is the first dot-
            # segment. The builder lets users override via explicit `frame_filter:`.
            self.frame_filter = self.signal.split(".", 1)[0]


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
    # Output is a list of (namespace, signals) groups. One handler may write
    # to multiple output buses (e.g. publish a computed value to both the
    # primary CAN bus and a redundant backup bus). The recipe's value_expr
    # fans out to every signal across all groups; generated Python calls
    # restbus.update_signals() once per group. For single-output handlers
    # (the common case), output_groups has exactly one entry.
    output_groups: list[OutputGroupIR] = field(default_factory=list)
    state: StateIR | None = None  # Optional state variable
    periodic_task: PeriodicTaskIR | None = None  # Optional periodic task
    threshold: float | None = None  # Optional threshold for ThresholdMapping
    operator: str | None = None  # Optional comparison operator (default ">")
    true_when: str | None = None  # Optional direction: "above" (default) | "below"
    # WeightedLogOdds fields (NEW). When pattern == "WeightedLogOdds" the recipe
    # consumes these instead of input_signals. weighted_inputs lets a single
    # handler fan-in from multiple CAN namespaces (e.g. CAD_logic reads seat,
    # camera, and airbag status from three different buses) — unlike input_signals
    # which assumes a single triggering frame.
    weighted_inputs: list[WeightedInputIR] = field(default_factory=list)
    weighted_threshold: float | None = None  # Decision threshold for the sum.
    # Flat pattern params extracted from a list-form `pattern:` block (e.g. the
    # ThresholdMapping spec in inc_schema/SWC_seat_sensors_preprocessing.yaml
    # embeds threshold/operator/true_when inside the pattern entry instead of
    # flat on the handler). Populated by the builder; remains empty for the
    # legacy string-form `pattern:`.
    pattern_params: dict = field(default_factory=dict)


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

    def __post_init__(self):
        """Resolve python_var_name collisions across the model's namespaces.

        Two namespaces in the same model can have IDENTICAL suffixes
        (e.g. "CENTRAL-CpdCan0" and "DMS-CpdCan0" both → "cpd_can_0") — this
        makes the generated class definition ambiguous and crashes the
        generated Python at `__init__` (positional vs keyword collision).
        We detect collisions on the default-derived name and disambiguate the
        LATER entries by prepending a snake_case form of the ECU prefix.

        Examples (CENTRAL/DMS/AIRBAG share `CpdCan0`):
            CENTRAL-CpdCan0 → cpd_can_0            (kept; first wins)
            DMS-CpdCan0     → dms_cpd_can_0        (disambiguated)
            AIRBAG-CpdCan0  → airbag_cpd_can_0     (disambiguated)

        Single-namespace ECUs and the historical "BodyCan0 vs DriverCan0" case
        are unaffected (suffixes are already unique so the early-return wins).
        """
        counts: dict[str, int] = {}
        for ns in self.namespaces:
            base = ns.python_var_name
            counts[base] = counts.get(base, 0) + 1
        if not any(c > 1 for c in counts.values()):
            return  # no collisions; keep default names → byte-identical output

        seen: set[str] = set()
        for ns in self.namespaces:
            base = ns.python_var_name
            if base in seen:
                # Collision: derive a unique name from the ECU prefix.
                prefix_snake = _ecu_prefix_to_snake(ns.name)
                candidate = f"{prefix_snake}_{base}"
                # Defensive: keep appending `_v2`/etc. if still colliding
                # (shouldn't happen since prefixes are unique, but guard).
                n = 2
                while candidate in seen:
                    candidate = f"{candidate}_v{n}"
                    n += 1
                ns.python_var_name = candidate
            seen.add(ns.python_var_name)


def _ecu_prefix_to_snake(namespace_name: str) -> str:
    """Convert the ECU prefix (the part before `-`) to snake_case.

    E.g., "AIRBAG-CpdCan0" → "airbag"
          "DMS-CpdCan0"     → "dms"
          "BCM-BodyCan0"    → "bcm"
    """
    prefix = namespace_name.split("-", 1)[0]
    out: list[str] = []
    for i, ch in enumerate(prefix):
        if ch.isupper() and i > 0 and not prefix[i - 1].isupper():
            out.append("_")
        if ch.isupper():
            out.append(ch.lower())
        else:
            out.append(ch)
    # Collapse "BCR_Driver" → "bcr_driver" (already a snake from underscore
    # inserts above; no further work needed).
    return "".join(out)


def _derive_python_var_name(namespace_name: str) -> str:
    """Convert a Remotive namespace name to a Python snake_case variable name.

    E.g., "BCM-BodyCan0" → "body_can_0"
         "BCM-DriverCan0" → "driver_can_0"
         "SEAT-OCS-CpdCan0" → "ocs_cpd_can_0"  (multi-segment suffix after ECU prefix)

    The convention follows the reference examples where "BCM-BodyCan0" is
    accessed as `self.body_can_0` in Python code. Any remaining hyphens in the
    suffix (e.g. "OCS-CpdCan0") become underscores so the result is a valid
    Python identifier.
    """
    # Remove the ECU prefix (e.g., "BCM-" / "SEAT-") and convert to snake_case.
    # Only the FIRST hyphen separates ECU prefix from suffix; further hyphens
    # inside the suffix are converted to underscores below.
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
        # Hyphens inside the suffix (e.g. "OCS-CpdCan0") → underscore
        if char == "-":
            result.append("_")
        else:
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
