"""IR builder — converts a raw spec dict into validated BehavioralModelIR.

The builder is responsible for:
1. Extracting fields from the raw dict and constructing IR dataclasses
2. Deriving computed fields (python_var_names, value_exprs)
3. Running validators on the constructed IR
4. Returning a validated BehavioralModelIR or raising on violations
"""

from __future__ import annotations

from pathlib import Path

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
    WeightedInputIR,
)
from bmgen.ir.validators import ValidationViolation, has_errors, validate, validate_namespace_types


class BuilderError(Exception):
    """Raised when the builder cannot construct a valid IR from the spec."""

    def __init__(self, violations: list[ValidationViolation]):
        self.violations = violations
        messages = "\n".join(f"  [{v.severity}] {v.rule}: {v.message}" for v in violations)
        super().__init__(f"IR validation failed with {len(violations)} violations:\n{messages}")


def _compose_software_components(
    spec: dict,
    base_dir: str | Path | None,
) -> dict:
    """Resolve `software_components:` by recursively merging child SWC YAML files.

    New schema (inc_schema/): a parent ECU file declares `ecu:` + `namespace_types:`
    + `software_components: [<relpath>, ...]`. Each child is an SWC YAML file
    carrying its own `handlers:` and/or `websocket_listeners:` — it inherits the
    parent's namespace_types without redeclaring them. This mirrors the AUTOSAR
    "ECU extract → SWC composition" pattern, where one ECU can host several
    software components.

    Merge rules:
      1. handlers[]            : concatenated from all SWCs (in declaration order).
      2. websocket_listeners[] : concatenated from all SWCs.
      3. namespace_types{}     : parent + children merged; child keys win on conflict.
      4. ecu/model/reset_handler/etc: only the parent declares these. SWC files
         must NOT re-declare them — that would be an ambiguity.
      5. software_components: key is dropped after merge (it's just the inclusion
         list, no semantic meaning once flattened).

    If the spec has no `software_components:`, it is returned unchanged so the
    old single-file path is byte-identical.

    Args:
        spec: Raw spec dict (already YAML-parsed, in-memory).
        base_dir: Filesystem root for resolving relative SWC paths. If None,
            relative paths raise a clear error.

    Returns:
        A new spec dict (the input is not mutated) with `software_components:`
        resolved — equivalent to the old single-file shape.

    Raises:
        BuilderError: If a child file cannot be found/parsed, declares forbidden
            top-level keys, or contains duplicate handler/listener names.
    """
    from pathlib import Path

    from bmgen.ir.parser import parse_yaml_file

    swc_refs = spec.get("software_components")
    if not swc_refs:
        return spec  # fast path: old single-file spec, untouched

    if not isinstance(swc_refs, list):
        raise BuilderError([
            ValidationViolation(
                rule="software_components_must_be_list",
                message="`software_components:` must be a list of YAML file paths",
            )
        ])

    if base_dir is None:
        raise BuilderError([
            ValidationViolation(
                rule="software_components_base_dir_missing",
                message=(
                    "`software_components:` references were found but the builder was "
                    "called without base_dir; pass Path(yaml_file).parent to resolve them. "
                    "Aborting — use bmgen.cli (which already does this) or build_ir(..., base_dir=...)"
                ),
            )
        ])

    base = Path(base_dir)

    # Forbidden keys in a SWC child (parent owns these exclusively).
    # `namespace_types` IS allowed in a SWC child (for declarations unique to
    # that component) — but those declarations merge into the parent's, so
    # it's purely additive. `namespaces:` is the deprecated old form and is
    # forbidden everywhere (parent already dropped it).
    swc_forbidden = {
        "model", "ecu", "reset_handler", "namespaces",
        "novel_logic_handlers", "software_components",
    }

    merged_handlers: list[dict] = []
    merged_ws: list[dict] = []
    merged_types: dict[str, str] = dict(spec.get("namespace_types", {}) or {})

    for ref in swc_refs:
        if not isinstance(ref, str) or not ref:
            raise BuilderError([
                ValidationViolation(
                    rule="software_components_invalid_entry",
                    message=f"`software_components:` entry must be a non-empty string path, got {ref!r}",
                )
            ])

        path = Path(ref)
        if not path.is_absolute():
            path = (base / path).resolve()

        if not path.exists():
            raise BuilderError([
                ValidationViolation(
                    rule="software_components_file_not_found",
                    message=f"Software component file not found: {ref!r} (resolved to {path})",
                )
            ])

        try:
            child_spec = parse_yaml_file(str(path))
        except Exception as e:
            raise BuilderError([
                ValidationViolation(
                    rule="software_components_parse_failed",
                    message=f"Failed to parse SWC file {ref!r}: {e}",
                )
            ])

        forbidden_present = swc_forbidden & set(child_spec.keys())
        if forbidden_present:
            raise BuilderError([
                ValidationViolation(
                    rule="software_components_forbidden_keys",
                    message=(
                        f"SWC file {ref!r} declares forbidden top-level keys "
                        f"{sorted(forbidden_present)}. The parent ECU file owns these; "
                        f"SWC files may only declare `handlers:` and/or `websocket_listeners:` "
                        f"(plus optional `namespace_types:` overrides)."
                    ),
                )
            ])

        # namespace_types merge: child keys override parent on conflict.
        for k, v in (child_spec.get("namespace_types") or {}).items():
            merged_types[k] = v

        merged_handlers.extend(child_spec.get("handlers", []) or [])
        merged_ws.extend(child_spec.get("websocket_listeners", []) or [])

    # Check handler-name uniqueness across the entire merge (parent + all SWCs).
    handler_names: list[str] = []
    for h in spec.get("handlers", []) or []:
        if h.get("name"):
            handler_names.append(h["name"])
    for h in merged_handlers:
        if h.get("name"):
            handler_names.append(h["name"])
    dupes = sorted({n for n in handler_names if handler_names.count(n) > 1})
    if dupes:
        raise BuilderError([
            ValidationViolation(
                rule="software_components_duplicate_handler_names",
                message=f"Duplicate handler names across SWC files: {dupes}",
            )
        ])

    # Build the post-merge spec (don't mutate caller's dict).
    new_spec = dict(spec)
    new_spec["handlers"] = list(spec.get("handlers", []) or []) + merged_handlers
    if merged_ws or spec.get("websocket_listeners"):
        new_spec["websocket_listeners"] = (
            list(spec.get("websocket_listeners", []) or []) + merged_ws
        )
    new_spec["namespace_types"] = merged_types
    new_spec.pop("software_components", None)  # resolved
    return new_spec


def build_ir(
    spec: dict,
    base_dir: str | Path | None = None,
) -> BehavioralModelIR:
    """Build a validated BehavioralModelIR from a raw spec dict.

    Args:
        spec: Raw Python dict from the YAML parser.
        base_dir: Optional filesystem root used to resolve `software_components:`
            relative paths (new SWC-composition schema). If None, SWC refs must
            be absolute paths. The CLI passes `Path(yaml_file).parent`.

    Returns:
        Validated BehavioralModelIR ready for the compiler.

    Raises:
        BuilderError: If any invariant violations are found.
        ValueError: If required top-level fields are missing.
    """
    # Resolve SWC composition BEFORE we touch handlers: the parent ECU file may
    # only carry `ecu:` + `software_components:`, with the actual handlers and
    # websocket_listeners living in the child SWC files. After merging, the
    # in-memory dict looks exactly like a flat single-file spec (back-compat).
    spec = _compose_software_components(spec, base_dir)

    # Extract top-level model info. Two top-level shapes are accepted:
    #   - old / service_oriented:  `model: {name, ecu_name}`
    #   - SWC-style (inc_schema/): `ecu:  {name, broker_name}`
    # Both produce identical IR fields — `broker_name` maps to `ecu_name`
    # (broker_name is the canonical terminology in the new schema but the
    # rest of the compiler still calls it ecu_name).
    model_spec = spec.get("model") or spec.get("ecu")
    if model_spec is None:
        raise ValueError(
            "YAML spec must contain a 'model' or 'ecu' section "
            "(new schema uses 'ecu:' with 'name' and 'broker_name')"
        )

    model_name = model_spec.get("name")
    ecu_name = model_spec.get("ecu_name") or model_spec.get("broker_name")
    if not model_name or not ecu_name:
        raise ValueError(
            "Model/ecu section must contain 'name' and 'ecu_name' (or 'broker_name')"
        )

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
    4. weighted_inputs[] namespaces are ALSO refs (each is 'as_input') — so a
       WeightedLogOdds handler reading from N namespaces correctly registers all
       N. Without this, a fan-in handler would silently leave its source
       namespaces out of the IR and `_check_handler_input_namespace_exists`
       would 404.
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
        for w in h.weighted_inputs:
            _mark(w.namespace, "as_input")
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
    """Build HandlerIR objects from raw handler spec dicts.

    Accepts three input shapes:
      A. Legacy single-input:   `input: {namespace, frame_filter?, signal|signals}`
      B. WeightedLogOdds fan-in (new): `input: [{namespace, signal, frame_filter?}, ...]`
                                    + top-level `weights: {signal: float, ...}`
                                    + `threshold:` (decision cutoff)
      C. Pattern-as-list (new): `pattern: [{name: ThresholdMapping, threshold: 8,
         operator: ">=", true_when: below}, ...]` — the YAML's first list entry's
         name is the recipe name; its other keys are flat params merged into the
         handler via `pattern_params` and applied to the matching typed fields
         (threshold/operator/true_when). Only the first list entry is consumed;
         the rest are ignored (the YAML uses a single-element list purely as a
         wrapper for the embedded params).
    """
    handlers = []
    for h_spec in handler_specs:
        name = h_spec.get("name")
        if not name:
            raise ValueError("Each handler must have a 'name' field")

        # Resolve `pattern:` — accept string OR single-element dict-list.
        # The list form carries embedded params (threshold/operator/true_when
        # inside the pattern entry, not flat on the handler). The first list
        # entry's `name` is the recipe name; the rest are flat params.
        pattern_raw = h_spec.get("pattern")
        pattern_params: dict = {}
        if isinstance(pattern_raw, list):
            if not pattern_raw or not isinstance(pattern_raw[0], dict):
                raise ValueError(
                    f"Handler '{name}' pattern list must start with a mapping; got {pattern_raw!r}"
                )
            first = pattern_raw[0]
            pattern = first.get("name")
            if not pattern:
                raise ValueError(
                    f"Handler '{name}' pattern entry is missing required 'name' key"
                )
            # Capture every other key as a flat param (ThresholdMapping consumes
            # threshold/operator/true_when here; future patterns can do the same).
            pattern_params = {k: v for k, v in first.items() if k != "name"}
        else:
            pattern = pattern_raw
        if not pattern:
            raise ValueError(f"Handler '{name}' must have a 'pattern' field")

        novel_logic = h_spec.get("novel_logic", False)

        # ── Input handling ────────────────────────────────────────────────
        # Three shapes: scalar-input (legacy), signals-list (legacy), or
        # weighted-input list (WeightedLogOdds fan-in).
        input_spec = h_spec.get("input")
        input_namespace = ""
        input_frame_filter = ""
        input_signals: list[InputSignalIR] = []
        weighted_inputs: list[WeightedInputIR] = []
        weighted_threshold: float | None = None

        if isinstance(input_spec, list):
            # Fan-in shape: list of {namespace, signal, frame_filter?, weight?}.
            # weight is allowed per-entry but typically lives at the top level
            # under `weights:` (the SWC_CAD_logic shape); we accept both for
            # forward-compat.
            for entry in input_spec:
                if not isinstance(entry, dict):
                    raise ValueError(
                        f"Handler '{name}' input list entries must be mappings, got {entry!r}"
                    )
                ns = entry.get("namespace", "")
                sig = entry.get("signal", "")
                if not ns or not sig:
                    raise ValueError(
                        f"Handler '{name}' input list entries must have both 'namespace' and 'signal'; got {entry!r}"
                    )
                explicit_ff = entry.get("frame_filter", "")
                inferred_ff = sig.split(".", 1)[0]
                weighted_inputs.append(WeightedInputIR(
                    namespace=ns,
                    signal=sig,
                    weight=float(entry.get("weight", 0.0)),
                    frame_filter=(explicit_ff or inferred_ff),
                ))
            _ensure_unique_weighted_var_names(weighted_inputs)

            # weighted_threshold: prefer top-level `threshold:`, fall back to
            # pattern_params['threshold'] (embedded-param form), else None.
            weighted_threshold = h_spec.get("threshold")
            if weighted_threshold is None and "threshold" in pattern_params:
                weighted_threshold = float(pattern_params["threshold"])

        elif isinstance(input_spec, dict):
            input_namespace = input_spec.get("namespace", "")
            explicit_ff = input_spec.get("frame_filter", "")
            input_frame_filter = explicit_ff  # may be empty → infer per signal

            # Build input signals (scalar `signal` and list `signals` both allowed).
            input_signal_names: list[str] = []
            scalar_signal = input_spec.get("signal")
            if scalar_signal:
                input_signal_names.append(scalar_signal)
            input_signal_names.extend(input_spec.get("signals", []))

            input_signals = [InputSignalIR(name=s) for s in input_signal_names]
            _ensure_unique_var_names(input_signals)

            # Frame inference: when frame_filter is OMITTED in the YAML, infer
            # the frame name from the first signal's first dot-segment. This
            # is the project convention — every signal is "<Frame>.<Signal>",
            # so the frame name is unambiguous. We store the inferred value
            # on the IR (so downstream code and tests see one source of truth).
            # When frame_filter IS explicit, keep the user's value verbatim.
            if not input_frame_filter and input_signal_names:
                input_frame_filter = input_signal_names[0].split(".", 1)[0]
        elif input_spec is None:
            # No input block — fine for novel_logic handlers / future patterns.
            pass
        else:
            raise ValueError(
                f"Handler '{name}' input must be a dict or a list of dicts; "
                f"got {type(input_spec).__name__}"
            )

        # ── Output handling ───────────────────────────────────────────────
        # Accepted as either a list of {namespace, signals} groups (new schema)
        # or a single {namespace, signals} dict (old schema, wrapped into a
        # one-element list for migration back-compat).
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
        elif pattern == "ActuatorCommand":
            # Auto-synthesise last-seen state from pattern_params so SWC authors
            # don't need an explicit `state:` block. Defaults match the SE
            # on_seat_cmd simulate path: int last-pos, initial -1, reset -1.
            _vt = pattern_params.get("value_type", "int")
            if _vt not in ("int", "float", "bool", "str"):
                _vt = "int"
            _defaults = {"int": -1, "float": -1.0, "bool": False, "str": ""}
            _init = pattern_params.get("initial_state", _defaults[_vt])
            try:
                if _vt == "int":
                    _init = int(_init)
                elif _vt == "float":
                    _init = float(_init)
                elif _vt == "bool":
                    _init = bool(_init)
                else:
                    _init = str(_init)
            except (TypeError, ValueError):
                _init = _defaults[_vt]
            state_ir = StateIR(
                name=f"last_{name}",
                type=_vt,
                initial=_init,
                reset_value=_init,
                owner=name,
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

        # Threshold (for ThresholdMapping pattern). Three sources, in priority:
        #   1. handler-level `threshold:` key (legacy explicit form)
        #   2. pattern_params['threshold'] (list-form-embedded form)
        #   3. None (recipe treats as missing → ValidationViolation Invariant 11)
        threshold = h_spec.get("threshold")
        if threshold is None and "threshold" in pattern_params:
            threshold = float(pattern_params["threshold"])

        # Operator / true_when: same dual-source resolution (flat key OR embedded).
        operator = h_spec.get("operator")
        if operator is None and "operator" in pattern_params:
            operator = pattern_params["operator"]
        true_when = h_spec.get("true_when")
        if true_when is None and "true_when" in pattern_params:
            true_when = pattern_params["true_when"]

        # WeightedLogOdds params: read `weights:` (legacy explicit form) OR
        # pattern_params['weights'] (list-form embedded). The signal-key in the
        # weights map is the FULL signal name (e.g. "SeatInput.SeatOccupied"),
        # which is how SWC_CAD_logic.yaml authors it.
        weights_top = h_spec.get("weights")
        weights_pp = pattern_params.get("weights")
        weights_map: dict[str, float] = {}
        if isinstance(weights_top, dict):
            weights_map.update({k: float(v) for k, v in weights_top.items()})
        if isinstance(weights_pp, dict):
            weights_map.update({k: float(v) for k, v in weights_pp.items()})

        # Apply weights_map to weighted_inputs (by signal name match).
        if weighted_inputs and weights_map:
            for wi in weighted_inputs:
                if wi.weight == 0.0 and wi.signal in weights_map:
                    wi.weight = float(weights_map[wi.signal])

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
                weighted_inputs=weighted_inputs,
                weighted_threshold=weighted_threshold,
                pattern_params=pattern_params,
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


def _ensure_unique_weighted_var_names(weighted_inputs: list[WeightedInputIR]) -> None:
    """Disambiguate Python variable names across weighted_inputs.

    Same collision rule as `_ensure_unique_var_names` but applied to
    WeightedInputIR. With multi-namespace fan-in, two inputs from DIFFERENT
    namespaces can still have the same frame name (e.g. a "Status" frame on
    both CAN0 and CAN1) and would collide on the default var name. The
    disambiguator uses the signal-name fragment to keep the local variables
    readable in the generated handler body.
    """
    seen: dict[str, int] = {}
    for wi in weighted_inputs:
        base = wi.python_var_name
        seen[base] = seen.get(base, 0) + 1

    counts: dict[str, int] = {}
    for wi in weighted_inputs:
        base = wi.python_var_name
        if seen[base] == 1:
            continue
        parts = wi.signal.split(".", 1)
        suffix = parts[1] if len(parts) == 2 else parts[0]
        suffix_snake = _camel_to_snake(suffix)
        candidate = f"{base.removesuffix('_signal')}_{suffix_snake}_signal"
        counts[candidate] = counts.get(candidate, 0) + 1
        if counts[candidate] > 1:
            candidate = f"{candidate}_{counts[candidate]}"
        wi.python_var_name = candidate


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
