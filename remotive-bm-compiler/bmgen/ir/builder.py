"""IR builder — converts a raw spec dict into validated BehavioralModelIR.

The builder is responsible for:
1. Extracting fields from the raw dict and constructing IR dataclasses
2. Deriving computed fields (python_var_names, value_exprs)
3. Running validators on the constructed IR
4. Returning a validated BehavioralModelIR or raising on violations
"""

from __future__ import annotations

from bmgen.ir.model import (
    BehavioralModelIR,
    HandlerIR,
    InputSignalIR,
    NamespaceIR,
    OutputSignalIR,
    PeriodicTaskIR,
    ResetHandlerIR,
    RestbusConfigIR,
    StateIR,
    WebsocketListenerIR,
)
from bmgen.ir.validators import ValidationViolation, has_errors, validate


class BuilderError(Exception):
    """Raised when the builder cannot construct a valid IR from the spec."""

    def __init__(self, violations: list[ValidationViolation]):
        self.violations = violations
        messages = "\n".join(f"  [{v.severity}] {v.rule}: {v.message}" for v in violations)
        super().__init__(f"IR validation failed with {len(violations)} violations:\n{messages}")


def build_ir(spec: dict) -> BehavioralModelIR:
    """Build a validated BehavioralModelIR from a raw spec dict.

    Args:
        spec: Raw Python dict from the YAML parser.

    Returns:
        Validated BehavioralModelIR ready for the compiler.

    Raises:
        BuilderError: If any invariant violations are found.
        ValueError: If required top-level fields are missing.
    """
    # Extract top-level model info
    model_spec = spec.get("model")
    if model_spec is None:
        raise ValueError("YAML spec must contain a 'model' section")

    model_name = model_spec.get("name")
    ecu_name = model_spec.get("ecu_name")
    if not model_name or not ecu_name:
        raise ValueError("Model section must contain 'name' and 'ecu_name'")

    # Build namespaces
    namespace_specs = spec.get("namespaces", [])
    namespaces = _build_namespaces(namespace_specs)

    # Build handlers
    handler_specs = spec.get("handlers", [])
    handlers = _build_handlers(handler_specs)

    # Build reset handler
    reset_handler = _build_reset_handler(spec, handlers)

    # Build model-level websocket listeners (external ws → CAN restbus).
    # Sibling to handlers — NOT inside handlers[]; a listener has no CAN frame.
    websocket_listeners = _build_websocket_listeners(spec.get("websocket_listeners", []))

    # Collect novel_logic handler names
    novel_logic_handlers = [h.name for h in handlers if h.novel_logic]

    # Construct the IR
    ir = BehavioralModelIR(
        name=model_name,
        ecu_name=ecu_name,
        namespaces=namespaces,
        handlers=handlers,
        reset_handler=reset_handler,
        novel_logic_handlers=novel_logic_handlers,
        websocket_listeners=websocket_listeners,
    )

    # Validate the IR
    violations = validate(ir)
    if has_errors(violations):
        raise BuilderError(violations)

    # Apply recipe-derived value_exprs to output signals
    _apply_value_exprs(ir)

    return ir


def _build_namespaces(namespace_specs: list[dict]) -> list[NamespaceIR]:
    """Build NamespaceIR objects from raw namespace spec dicts."""
    namespaces = []
    for ns_spec in namespace_specs:
        name = ns_spec.get("name")
        if not name:
            raise ValueError("Each namespace must have a 'name' field")

        type_ = ns_spec.get("type", "can")
        role = ns_spec.get("role", "input")

        restbus_spec = ns_spec.get("restbus")
        restbus_ir = None
        if restbus_spec:
            restbus_ir = RestbusConfigIR(
                sender_filter=restbus_spec.get("sender_filter", ""),
            )

        namespaces.append(
            NamespaceIR(
                name=name,
                type=type_,
                role=role,
                restbus=restbus_ir,
                client_id=ns_spec.get("client_id"),
                interface_name=ns_spec.get("interface_name"),
            )
        )
    return namespaces


def _build_handlers(handler_specs: list[dict]) -> list[HandlerIR]:
    """Build HandlerIR objects from raw handler spec dicts."""
    handlers = []
    for h_spec in handler_specs:
        name = h_spec.get("name")
        if not name:
            raise ValueError("Each handler must have a 'name' field")

        pattern = h_spec.get("pattern")
        if not pattern:
            raise ValueError(f"Handler '{name}' must have a 'pattern' field")

        novel_logic = h_spec.get("novel_logic", False)

        # Input — accept either `signal` (scalar) or `signals` (list).
        # The IR field input_signals is already a list; multi-input patterns
        # (e.g. logic gates) read several signals from the one triggering frame.
        input_spec = h_spec.get("input", {})
        input_namespace = input_spec.get("namespace", "")
        input_frame_filter = input_spec.get("frame_filter", "")

        # Build input signals (scalar `signal` and list `signals` both allowed)
        input_signal_names = []
        scalar_signal = input_spec.get("signal")
        if scalar_signal:
            input_signal_names.append(scalar_signal)
        input_signal_names.extend(input_spec.get("signals", []))

        input_signals = [InputSignalIR(name=s) for s in input_signal_names]
        _ensure_unique_var_names(input_signals)

        # Output
        output_spec = h_spec.get("output", {})
        output_namespace = output_spec.get("namespace", "")
        output_signal_names = output_spec.get("signals", [])
        output_signals = [OutputSignalIR(name=s) for s in output_signal_names]

        # State
        state_spec = h_spec.get("state")
        state_ir = None
        if state_spec:
            state_ir = StateIR(
                name=state_spec.get("name", ""),
                type=state_spec.get("type", "bool"),
                initial=state_spec.get("initial", False),
                reset_value=state_spec.get("reset_value"),
                owner=state_spec.get("owner", name),
            )

        # Periodic task
        periodic_spec = h_spec.get("periodic_task")
        periodic_ir = None
        if periodic_spec:
            blink_output_spec = periodic_spec.get("blink_output", {})
            periodic_ir = PeriodicTaskIR(
                interval_sec=periodic_spec.get("interval_sec", 1.0),
                blink_output_namespace=blink_output_spec.get("namespace", output_namespace),
                blink_output_signals=blink_output_spec.get("signals", []),
                cleanup=periodic_spec.get("cleanup", False),
            )

        # Threshold (for ThresholdMapping pattern)
        threshold = h_spec.get("threshold")

        handlers.append(
            HandlerIR(
                name=name,
                pattern=pattern,
                novel_logic=novel_logic,
                input_namespace=input_namespace,
                input_frame_filter=input_frame_filter,
                input_signals=input_signals,
                output_namespace=output_namespace,
                output_signals=output_signals,
                state=state_ir,
                periodic_task=periodic_ir,
                threshold=threshold,
            )
        )
    return handlers


def _ensure_unique_var_names(input_signals: list[InputSignalIR]) -> None:
    """Disambiguate Python variable names across a handler's input signals.

    `_derive_signal_var_name` keys off the frame name only, so two signals in
    the same frame (e.g. "Logic.A" and "Logic.B") both derive to "logic_signal".
    For multi-input patterns this would shadow one variable with the next. Here
    we detect collisions and append a snake_case form of the signal's own name
    (the part after the dot) to make each variable unique and readable.
    """
    seen: dict[str, int] = {}
    for sig in input_signals:
        base = sig.python_var_name
        seen[base] = seen.get(base, 0) + 1

    counts: dict[str, int] = {}
    for sig in input_signals:
        base = sig.python_var_name
        if seen[base] == 1:
            continue  # unique already
        # Collision: append the signal-name part (after '.') for readability.
        parts = sig.name.split(".", 1)
        suffix = parts[1] if len(parts) == 2 else parts[0]
        suffix_snake = _camel_to_snake(suffix)
        candidate = f"{base.removesuffix('_signal')}_{suffix_snake}_signal"
        # Guard against a still-duplicate candidate with a numeric counter.
        counts[candidate] = counts.get(candidate, 0) + 1
        if counts[candidate] > 1:
            candidate = f"{candidate}_{counts[candidate]}"
        sig.python_var_name = candidate


def _camel_to_snake(name: str) -> str:
    """Convert a CamelCase signal-name fragment to snake_case."""
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def _build_reset_handler(spec: dict, handlers: list[HandlerIR]) -> ResetHandlerIR | None:
    """Build a ResetHandlerIR if the spec requests it or if any handler needs reset.

    A reset handler is auto-generated when:
    - The YAML spec explicitly sets `reset_handler: true`
    - Any handler has a state with a reset_value

    The reset handler resets all owned state variables and calls
    restbus.reset() on all output namespaces.
    """
    explicit_reset = spec.get("reset_handler", False)

    # Collect all states that have reset values
    states_with_reset = [h.state for h in handlers if h.state is not None and h.state.reset_value is not None]

    # Collect all output namespace names
    output_ns_names = []
    for ns_spec in spec.get("namespaces", []):
        if ns_spec.get("role") in ("output", "both") and ns_spec.get("restbus"):
            output_ns_names.append(ns_spec.get("name"))

    if explicit_reset or states_with_reset:
        return ResetHandlerIR(
            states_to_reset=states_with_reset,
            namespaces_to_reset=output_ns_names,
        )
    return None


def _build_websocket_listeners(ws_specs: list[dict]) -> list[WebsocketListenerIR]:
    """Build WebsocketListenerIR objects from raw websocket_listeners spec dicts.

    A websocket listener is a model-level concern (sibling to handlers/), not a
    handler: it runs a background asyncio task for the ECU's whole lifetime,
    bridging an external websocket stream onto a CAN output namespace's restbus.
    Namespace-existence and restbus checks are deferred to validators (Invariant
    12) — the builder only extracts fields here.
    """
    listeners: list[WebsocketListenerIR] = []
    for ws_spec in ws_specs:
        signal_map_spec = ws_spec.get("signal_map", []) or []
        signal_map = [
            (m.get("ws_key", ""), m.get("signal", ""))
            for m in signal_map_spec
        ]
        listeners.append(
            WebsocketListenerIR(
                name=ws_spec.get("name", ""),
                url=ws_spec.get("url", ""),
                output_namespace=ws_spec.get("output_namespace", ""),
                signal_map=signal_map,
                cleanup=ws_spec.get("cleanup", True),
                reconnect_delay_sec=float(ws_spec.get("reconnect_delay_sec", 2.0)),
            )
        )
    return listeners


def _apply_value_exprs(ir: BehavioralModelIR) -> None:
    """Apply recipe-derived value expressions to output signals.

    This step fills in the `value_expr` field on OutputSignalIR. The expression
    is owned by each recipe via Recipe.output_value_expr(), so adding a new
    pattern requires no edit here — the registry is the single source of truth.

    novel_logic handlers are skipped (they generate stubs with no logic).
    Unknown patterns are left with empty value_exprs; validators reject them
    earlier unless novel_logic=True, so this is only reached for known recipes.
    """
    from bmgen.recipes.registry import create_default_registry

    registry = create_default_registry()

    for handler in ir.handlers:
        if handler.novel_logic:
            # novel_logic handlers have no value expressions (stub only)
            continue

        recipe = registry.get(handler.pattern)
        if recipe is None:
            continue

        value_expr = recipe.output_value_expr(handler)
        for output_signal in handler.output_signals:
            output_signal.value_expr = value_expr
