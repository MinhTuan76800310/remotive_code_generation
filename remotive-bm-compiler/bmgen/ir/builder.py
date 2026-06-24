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
    OutputGroupIR,
    OutputSignalIR,
    PeriodicTaskIR,
    ResetHandlerIR,
    RestbusConfigIR,
    StateIR,
    WebsocketListenerIR,
)
from bmgen.ir.validators import ValidationViolation, has_errors, validate, validate_namespace_types


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

    # Build handlers
    handler_specs = spec.get("handlers", [])
    handlers = _build_handlers(handler_specs)

    # Build model-level websocket listeners (external ws → CAN restbus).
    # Sibling to handlers — NOT inside handlers[]; a listener has no CAN frame.
    websocket_listeners = _build_websocket_listeners(spec.get("websocket_listeners", []))

    # Backward-compat: if the old top-level `namespaces:` key is present alongside
    # (or instead of) `namespace_types:`, warn and (only if no `namespace_types:`)
    # still validate the user didn't drift. Inference below does not depend on
    # the old key — every namespace is reconstructed from handler/ws refs.
    if "namespaces" in spec:
        import warnings
        warnings.warn(
            "Top-level `namespaces:` is deprecated and ignored; use `namespace_types:` "
            "(map of name → type). Namespaces are now inferred from handler/ws "
            "references. Remove `namespaces:` from this spec.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Reject duplicates in the old block up-front. Inference won't see them
        # (the block is ignored) and Invariant 1 only inspects the inferred IR,
        # so without this check a malformed deprecated spec would silently pass.
        old_names = [ns.get("name") for ns in spec["namespaces"] if ns.get("name")]
        dupes = sorted({n for n in old_names if old_names.count(n) > 1})
        if dupes:
            raise BuilderError([
                ValidationViolation(
                    rule="namespace_names_unique",
                    message=(
                        f"Duplicate namespace names in deprecated `namespaces:` block: "
                        f"{dupes}. Remove duplicates or migrate to `namespace_types:` "
                        f"(deduped by key)."
                    ),
                )
            ])

    # Infer namespaces from handler/ws references and the `namespace_types:` map.
    namespaces = _infer_namespaces(spec, handlers, websocket_listeners, ecu_name)

    # Build reset handler (uses inferred namespaces, not spec["namespaces"]).
    reset_handler = _build_reset_handler(
        explicit_reset=spec.get("reset_handler", False),
        handlers=handlers,
        namespaces=namespaces,
    )

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

    # Validate the IR — first the namespace_types map (needs raw spec), then the IR itself.
    namespace_type_violations = validate_namespace_types(spec, ir)
    ir_violations = validate(ir)
    violations = namespace_type_violations + ir_violations
    if has_errors(violations):
        raise BuilderError(violations)

    # Apply recipe-derived value_exprs to output signals
    _apply_value_exprs(ir)

    return ir


def _infer_namespaces(
    spec: dict,
    handlers: list[HandlerIR],
    ws_listeners: list[WebsocketListenerIR],
    ecu_name: str,
) -> list[NamespaceIR]:
    """Infer NamespaceIRs from handler/ws references and the namespace_types map.

    The new schema (`namespace_types:`) is a flat map of name → type. The old
    `namespaces:` list is deprecated and ignored at this stage (the warning is
    emitted in build_ir before this call).

    Inference rules:
    1. Collect refs: every handler's input_namespace is a name + 'as_input'
       mark; every output_group.namespace and every ws.output_namespace is a
       name + 'as_output' mark.
    2. role:  'both' if both as_input and as_output; 'input' if only as_input;
              'output' if only as_output.
    3. restbus: auto-created (RestbusConfigIR(sender_filter=ecu_name)) iff role
       is 'output' or 'both'. Validators enforce strict-required presence in
       `namespace_types:` for every ref and reject unknown type values.
    """
    type_map: dict[str, str] = spec.get("namespace_types", {}) or {}

    refs: dict[str, dict[str, bool]] = {}

    def _mark(name: str, kind: str) -> None:
        if not name:
            return
        r = refs.setdefault(name, {"as_input": False, "as_output": False})
        r[kind] = True

    for h in handlers:
        _mark(h.input_namespace, "as_input")
        for g in h.output_groups:
            _mark(g.namespace, "as_output")
    for ws in ws_listeners:
        _mark(ws.output_namespace, "as_output")

    result: list[NamespaceIR] = []
    for name, flags in refs.items():
        role = (
            "both" if flags["as_input"] and flags["as_output"]
            else "input" if flags["as_input"]
            else "output"
        )
        restbus_ir = (
            RestbusConfigIR(sender_filter=ecu_name)
            if role in ("output", "both")
            else None
        )
        result.append(
            NamespaceIR(
                name=name,
                type=type_map.get(name, "can"),
                role=role,
                restbus=restbus_ir,
            )
        )
    return result


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

        # Output — accepted as either a list of {namespace, signals} groups
        # (new schema) or a single {namespace, signals} dict (old schema,
        # wrapped into a one-element list for migration back-compat).
        output_spec = h_spec.get("output", [])
        if isinstance(output_spec, dict):
            output_specs = [output_spec]
        elif isinstance(output_spec, list):
            output_specs = output_spec
        else:
            raise ValueError(
                f"Handler '{name}' output must be a list of {{namespace, signals}} "
                f"groups (or a single dict for back-compat); got {type(output_spec).__name__}"
            )

        output_groups: list[OutputGroupIR] = []
        for group_spec in output_specs:
            group_ns = group_spec.get("namespace", "")
            group_signal_names = group_spec.get("signals", [])
            output_groups.append(
                OutputGroupIR(
                    namespace=group_ns,
                    signals=[OutputSignalIR(name=s) for s in group_signal_names],
                )
            )

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
            # Fall back to the first output group's namespace if the blink
            # output namespace wasn't specified explicitly.
            default_ns = (
                output_groups[0].namespace if output_groups else ""
            )
            periodic_ir = PeriodicTaskIR(
                interval_sec=periodic_spec.get("interval_sec", 1.0),
                blink_output_namespace=blink_output_spec.get("namespace", default_ns),
                blink_output_signals=blink_output_spec.get("signals", []),
                cleanup=periodic_spec.get("cleanup", False),
            )

        # Threshold (for ThresholdMapping pattern)
        threshold = h_spec.get("threshold")
        # Optional comparison operator + direction (for ThresholdMapping).
        # Both default to None → recipe treats absent as ">" / "above" so
        # existing specs render byte-identically.
        operator = h_spec.get("operator")
        true_when = h_spec.get("true_when")

        handlers.append(
            HandlerIR(
                name=name,
                pattern=pattern,
                novel_logic=novel_logic,
                input_namespace=input_namespace,
                input_frame_filter=input_frame_filter,
                input_signals=input_signals,
                output_groups=output_groups,
                state=state_ir,
                periodic_task=periodic_ir,
                threshold=threshold,
                operator=operator,
                true_when=true_when,
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


def _build_reset_handler(
    explicit_reset: bool,
    handlers: list[HandlerIR],
    namespaces: list[NamespaceIR],
) -> ResetHandlerIR | None:
    """Build a ResetHandlerIR if the spec requests it or if any handler needs reset.

    A reset handler is auto-generated when:
    - The YAML spec explicitly sets `reset_handler: true`
    - Any handler has a state with a reset_value

    The reset handler resets all owned state variables and calls
    restbus.reset() on all output namespaces (role 'output' or 'both').

    The `namespaces` arg is the *inferred* list of NamespaceIRs (from
    `_infer_namespaces`); the deprecated `spec["namespaces"]` is no longer
    read here — output namespaces come from role inference alone.
    """
    # Collect all states that have reset values
    states_with_reset = [
        h.state for h in handlers
        if h.state is not None and h.state.reset_value is not None
    ]

    # Collect all output namespace names from inferred IR
    output_ns_names = [ns.name for ns in namespaces if ns.role in ("output", "both")]

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

    This step fills in the `value_expr` field on every OutputSignalIR across
    every output_group. The expression is owned by each recipe via
    Recipe.output_value_expr(); a single expression fans out to every signal
    in every group. Adding a new pattern requires no edit here — the registry
    is the single source of truth.

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
        for group in handler.output_groups:
            for output_signal in group.signals:
                output_signal.value_expr = value_expr
