"""Context builder — merges IR + recipe contexts into a unified Jinja2 template context.

The context builder takes a validated BehavioralModelIR and recipe contexts,
and produces a single unified dict that the main.py.j2 template can consume.
This includes:
- Model-level variables (name, ecu_name)
- Namespace variables (python_var_names, restbus configs)
- Handler variables (names, template references, pattern contexts)
- Reset handler variables (states to reset, namespaces to reset)
"""

from __future__ import annotations

from bmgen.ir.model import BehavioralModelIR, HandlerIR, NamespaceIR
from bmgen.recipes.base import RecipeContext
from bmgen.recipes.registry import RecipeRegistry, create_default_registry


def build_template_context(
    ir: BehavioralModelIR,
    recipe_registry: RecipeRegistry | None = None,
) -> dict:
    """Build the unified Jinja2 template context from IR and recipe contexts.

    Args:
        ir: Validated BehavioralModelIR.
        recipe_registry: Recipe registry for pattern lookup. If None, uses default.

    Returns:
        Unified template context dict for main.py.j2 rendering.
    """
    if recipe_registry is None:
        recipe_registry = create_default_registry()

    # Model-level context
    context = {
        "model_name": ir.name,
        "model_name_lower": ir.name.lower(),
        "ecu_name": ir.ecu_name,
        "has_state": any(h.state is not None for h in ir.handlers),
        "has_reset_handler": ir.reset_handler is not None,
    }

    # Collect state variables for class definition
    states = []
    previous_states = []
    tickers = []
    for h in ir.handlers:
        if h.state is not None:
            state_type = "bool" if h.state.type == "bool" else h.state.type
            states.append({
                "name": h.state.name,
                "private_var": f"_{h.state.name}",
                "type": state_type,
                "initial": _python_repr(h.state.initial),
            })
            if h.pattern == "ToggleButtonState":
                previous_states.append({
                    "var_name": f"_previous_{h.state.name}",
                })
        if h.periodic_task is not None:
            tickers.append({
                "var_name": f"_ticker_{h.state.name}" if h.state else "_ticker",
            })

    context["states"] = states
    context["previous_states"] = previous_states
    context["tickers"] = tickers

    # Namespace context
    output_namespaces = [ns for ns in ir.namespaces if ns.role in ("output", "both")]
    input_only_namespaces = [ns for ns in ir.namespaces if ns.role == "input"]
    all_namespace_vars = ", ".join(ns.python_var_name for ns in ir.namespaces)

    context["output_namespaces"] = [
        {"name": ns.name, "python_var_name": ns.python_var_name, "restbus": ns.restbus}
        for ns in output_namespaces
    ]
    context["input_only_namespaces"] = [
        {"name": ns.name, "python_var_name": ns.python_var_name}
        for ns in input_only_namespaces
    ]
    context["all_namespace_vars"] = all_namespace_vars

    # Build namespace lookup: name → python_var_name
    ns_var_lookup = {ns.name: ns.python_var_name for ns in ir.namespaces}

    # Handler context — build per-handler recipe contexts
    handler_contexts = []
    for handler_ir in ir.handlers:
        recipe = recipe_registry.get(handler_ir.pattern)
        if recipe is None:
            # novel_logic handler — generate stub
            handler_ctx = _build_novel_logic_context(handler_ir, ns_var_lookup)
        else:
            # Validate handler against recipe
            errors = recipe.validate(handler_ir)
            if errors:
                raise ValueError(
                    f"Handler '{handler_ir.name}' failed recipe validation for '{handler_ir.pattern}': {errors}"
                )
            recipe_ctx = recipe.build_context(handler_ir)
            handler_ctx = _merge_recipe_context(handler_ir, recipe_ctx, ns_var_lookup)

        handler_contexts.append(handler_ctx)

    context["handlers"] = handler_contexts

    # Websocket listener context — model-level recipes (not per-handler).
    # Each listener is dispatched through the WebsocketBridge recipe, then its
    # output_namespace_var is resolved via ns_var_lookup (the recipe cannot do
    # this itself because the listener IR does not carry the namespace's
    # python_var_name — mirrors how _merge_recipe_context fills handler
    # output_namespace_var).
    websocket_listener_contexts = []
    for ws_ir in ir.websocket_listeners:
        recipe = recipe_registry.get("WebsocketBridge")
        if recipe is None:
            raise ValueError("WebsocketBridge recipe not registered")
        errors = recipe.validate(ws_ir)
        if errors:
            raise ValueError(f"Websocket listener '{ws_ir.name}' failed recipe validation: {errors}")
        ws_ctx = recipe.build_context(ws_ir)
        merged = dict(ws_ctx.context)
        merged["output_namespace_var"] = ns_var_lookup.get(ws_ir.output_namespace, "")
        # The handler_websocket template reads ws_output_namespace_var.
        merged["ws_output_namespace_var"] = ns_var_lookup.get(ws_ir.output_namespace, "")
        websocket_listener_contexts.append(merged)

    context["websocket_listeners"] = websocket_listener_contexts
    context["has_websocket_listeners"] = bool(websocket_listener_contexts)

    # Build input namespace var lookup for handlers
    handler_input_namespace_vars = {}
    for handler_ir in ir.handlers:
        handler_input_namespace_vars[handler_ir.name] = ns_var_lookup.get(handler_ir.input_namespace, "")

    context["handler_input_namespace_vars"] = handler_input_namespace_vars

    # Reset handler context
    if ir.reset_handler:
        reset_states = []
        for state in ir.reset_handler.states_to_reset:
            reset_states.append({
                "name": state.name,
                "private_var": f"_{state.name}",
                "reset_value": _python_repr(state.reset_value),
            })

        reset_namespace_vars = [
            ns_var_lookup.get(ns_name, "")
            for ns_name in ir.reset_handler.namespaces_to_reset
        ]

        context["reset_handler"] = {
            "states_to_reset": reset_states,
            "namespace_vars_to_reset": reset_namespace_vars,
        }
        context["reset_states"] = reset_states
        context["reset_namespace_vars"] = reset_namespace_vars

    return context


def _merge_recipe_context(
    handler_ir: HandlerIR,
    recipe_ctx: RecipeContext,
    ns_var_lookup: dict[str, str],
) -> dict:
    """Merge a recipe context with handler IR data and namespace lookups.

    This fills in the output_namespace_var and other namespace-dependent
    fields that the recipe cannot know on its own.
    """
    ctx = {
        "name": handler_ir.name,
        "pattern": handler_ir.pattern,
        "novel_logic": handler_ir.novel_logic,
        "template_name": recipe_ctx.template_name,
        "input_namespace": handler_ir.input_namespace,
        "input_namespace_var": ns_var_lookup.get(handler_ir.input_namespace, ""),
        "input_frame_filter": handler_ir.input_frame_filter,
        "output_namespace": handler_ir.output_namespace,
        "input_signals": [{"name": s.name, "python_var_name": s.python_var_name} for s in handler_ir.input_signals],
        "output_signals": [{"name": s.name, "value_expr": s.value_expr} for s in handler_ir.output_signals],
    }

    # Fill in output_namespace_var from recipe context or namespace lookup
    output_ns_var = recipe_ctx.context.get("output_namespace_var", "") or ns_var_lookup.get(handler_ir.output_namespace, "")
    recipe_ctx.context["output_namespace_var"] = output_ns_var
    ctx["output_namespace_var"] = output_ns_var

    # Merge all recipe-specific context fields
    ctx.update(recipe_ctx.context)

    return ctx


def _build_novel_logic_context(handler_ir: HandlerIR, ns_var_lookup: dict[str, str]) -> dict:
    """Build context for a novel_logic stub handler."""
    return {
        "name": handler_ir.name,
        "pattern": handler_ir.pattern,
        "novel_logic": True,
        "template_name": None,  # Novel logic handlers are inline in main.py.j2
        "input_namespace": handler_ir.input_namespace,
        "input_namespace_var": ns_var_lookup.get(handler_ir.input_namespace, ""),
        "input_frame_filter": handler_ir.input_frame_filter,
        "output_namespace": handler_ir.output_namespace,
        "output_namespace_var": ns_var_lookup.get(handler_ir.output_namespace, ""),
        "input_signals": [{"name": s.name, "python_var_name": s.python_var_name} for s in handler_ir.input_signals],
        "output_signals": [{"name": s.name, "value_expr": s.value_expr} for s in handler_ir.output_signals],
    }


def _python_repr(value) -> str:
    """Convert a Python value to its source code representation for templates."""
    if value is True:
        return "True"
    elif value is False:
        return "False"
    elif value is None:
        return "None"
    elif isinstance(value, str):
        return f'"{value}"'
    else:
        return repr(value)
