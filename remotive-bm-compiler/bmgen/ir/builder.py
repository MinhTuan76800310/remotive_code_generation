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

        # Input
        input_spec = h_spec.get("input", {})
        input_namespace = input_spec.get("namespace", "")
        input_frame_filter = input_spec.get("frame_filter", "")

        # Build input signals
        input_signal_name = input_spec.get("signal", "")
        input_signals = []
        if input_signal_name:
            input_signals.append(InputSignalIR(name=input_signal_name))

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
            )
        )
    return handlers


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


def _apply_value_exprs(ir: BehavioralModelIR) -> None:
    """Apply recipe-derived value expressions to output signals.

    This step fills in the `value_expr` field on OutputSignalIR based on the
    handler's pattern. It runs after IR construction because it depends on
    knowing the pattern and input signal variable names.
    """
    for handler in ir.handlers:
        if handler.novel_logic:
            # novel_logic handlers have no value expressions (stub only)
            continue

        if handler.pattern == "DirectSignalMapping":
            # DirectSignalMapping: output value = input signal value
            input_var = handler.input_signals[0].python_var_name if handler.input_signals else "value"
            for output_signal in handler.output_signals:
                output_signal.value_expr = input_var

        elif handler.pattern == "ToggleButtonState":
            # ToggleButtonState: output value = 1 if state_enabled else 0
            state_name = handler.state.name if handler.state else "enabled"
            for output_signal in handler.output_signals:
                output_signal.value_expr = f"1 if self._{state_name} else 0"

        elif handler.pattern == "PeriodicBlinkingOutput":
            # PeriodicBlinkingOutput: blink toggle handled by periodic task
            # The handler sets state, the periodic task toggles output
            state_name = handler.state.name if handler.state else "blink_enabled"
            for output_signal in handler.output_signals:
                output_signal.value_expr = f"1 if self._{state_name} else 0"
