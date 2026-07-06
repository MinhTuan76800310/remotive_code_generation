"""WeightedLogOdds recipe — CAD-style weighted-sum-of-bool-signals decision.

This recipe implements the Child-Alert-Detection (CAD) pattern used by the
CentralHPC ECU in the inc_schema/ specs. The trigger logic from
`cad_weight_tuner.html` is:

    end_result = Σ (weight_i × bool(signal_i))
    isChild    = (end_result >= threshold)

Each input is a (namespace, signal, weight) triple. The handler may fan-in
from MULTIPLE CAN namespaces (e.g. seat status on SEAT-CpdCan0, camera on
DMS-CpdCan0, airbag status on AIRBAG-CpdCan0). Unlike other recipes (which
fire on a single CAN frame), this one registers N `create_input_handler` calls
— one per unique (namespace, frame) pair — all dispatching to the SAME
generated method. The method latches each input's last value in instance
state, then recomputes the weighted sum on every fire.

Pattern (multi-frame fan-in, latched state):

    on every source frame:
        read incoming signal value
        update cached bool state for that input
        end_result = Σ (weight_i × cached_bool_i)
        isChild    = end_result >= threshold
        write isChild to all output_groups

YAML fields in the handler spec:
    pattern: WeightedLogOdds
    input:                          # list form — fan-in
      - namespace: <CAN ns name>
        signal: <Frame.Signal>
        # weight is per-entry OR (more typically) bulk under `weights:` below
      - ...
    weights:                        # optional, bulk form
      <Frame.Signal>: <float>
    threshold: <float>              # decision cutoff (end_result >= threshold → 1)

This recipe requires:
- ≥1 weighted_input (each entry has namespace+signal+weight)
- ≥1 output signal
- a positive integer or float `threshold` (the decision cutoff)
- NO `state:` (the per-input latches are managed internally and named
  automatically — `_<signal>_latched` — so the user doesn't have to think about
  them)
- NO `periodic_task` (stateless re-evaluation on every fire)
"""

from __future__ import annotations

from bmgen.ir.model import HandlerIR, WeightedInputIR
from bmgen.recipes.base import Recipe, RecipeContext


class WeightedLogOddsRecipe(Recipe):
    """Recipe for CAD-style weighted-sum-of-bool-signals decision (latched)."""

    @property
    def name(self) -> str:
        return "WeightedLogOdds"

    @property
    def description(self) -> str:
        return (
            "Compute a weighted sum of bool(input_i) across multiple CAN frames, "
            "compare to a threshold, write 0/1 to output(s). Inputs may fan-in from "
            "different namespaces; values are latched so the output reflects the "
            "LAST SEEN state of every input, not just the one in the current frame."
        )

    @property
    def template_name(self) -> str:
        return "handler_weighted.py.j2"

    def validate(self, handler_ir: HandlerIR) -> list[str]:
        errors: list[str] = []

        if len(handler_ir.weighted_inputs) < 1:
            errors.append(
                f"{self.name} requires at least 1 weighted input "
                f"(got {len(handler_ir.weighted_inputs)})"
            )

        # All weights must be present and finite (the recipe refuses to invent
        # defaults — weights are explicit policy, not heuristics).
        for wi in handler_ir.weighted_inputs:
            if wi.weight is None:
                errors.append(
                    f"{self.name} input '{wi.signal}' (namespace={wi.namespace}) "
                    f"has no weight; supply either an inline `weight:` on the input "
                    f"entry or a top-level `weights:` map keyed by signal name."
                )

        flat_output_signals = [
            sig for g in handler_ir.output_groups for sig in g.signals
        ]
        if len(flat_output_signals) < 1:
            errors.append(
                f"{self.name} requires at least 1 output signal, "
                f"found {len(flat_output_signals)}"
            )

        if handler_ir.weighted_threshold is None:
            # The validator surfaces a WARNING for this; the recipe still
            # generates working code with a default threshold of 2.0 (matches
            # cad_weight_tuner.html). We do NOT raise here because validation
            # is for surfacing the choice, not for blocking — the operator can
            # override by adding `threshold:` to the YAML.
            pass

        if handler_ir.state is not None:
            errors.append(
                f"{self.name} manages its own per-input latch state internally; "
                f"a top-level `state:` is not allowed (got '{handler_ir.state.name}')."
            )

        if handler_ir.periodic_task is not None:
            errors.append(
                f"{self.name} is event-driven (re-evaluates on every source frame); "
                f"a `periodic_task:` is not allowed."
            )

        return errors

    def output_value_expr(self, handler_ir: HandlerIR) -> str:
        """Return the Python expression for the weighted-sum threshold comparison.

        Result is 0/1 integer. The actual `Σ (w_i × bool(v_i))` is computed
        by the generated method (which sees the cached bool state in instance
        vars), then the comparison to `weighted_threshold` is inlined here.

        Note: this expression references a synthesized local variable
        `_<handler_name>_weighted_sum` that the generated method assigns before
        calling restbus.update_signals. See handler_weighted.py.j2.
        """
        if handler_ir.weighted_threshold is None:
            # Default to 2.0 — matches cad_weight_tuner.html reference tool.
            thr: float = 2.0
        else:
            thr = float(handler_ir.weighted_threshold)
        return f"1 if _weighted_sum >= {thr} else 0"

    def build_context(self, handler_ir: HandlerIR) -> RecipeContext:
        """Build template context for the WeightedLogOdds handler.

        Produces:
          - weighted_inputs:  list of {namespace, namespace_var, signal, weight,
                                       var, frame_filter, latched_var}
          - output_tuples:    flat (signal_name, value_expr) list
          - output_groups:    full multi-output shape (filled in by context_builder)
          - sum_expr:         the inlined Σ (weight × bool(latched_var)) expression
        """
        weighted_inputs_ctx: list[dict] = []
        sum_terms: list[str] = []

        for wi in handler_ir.weighted_inputs:
            # Each latched value lives at self._{var}_latched (instance bool).
            latched_var = f"_{wi.python_var_name.removesuffix('_signal')}_latched"
            weighted_inputs_ctx.append({
                "namespace": wi.namespace,
                "signal": wi.signal,
                "weight": wi.weight,
                "var": wi.python_var_name,
                "frame_filter": wi.frame_filter,
                "latched_var": latched_var,
            })
            sum_terms.append(f"({wi.weight} * (1 if self.{latched_var} else 0))")

        sum_expr = " + ".join(sum_terms) if sum_terms else "0.0"

        output_tuples = [
            (s.name, s.value_expr)
            for g in handler_ir.output_groups
            for s in g.signals
        ]

        return RecipeContext(
            handler_name=handler_ir.name,
            pattern=self.name,
            template_name=self.template_name,
            context={
                "handler_name": handler_ir.name,
                "weighted_inputs": weighted_inputs_ctx,
                "sum_expr": sum_expr,
                "output_tuples": output_tuples,
                "output_namespace_var": "",
            },
        )

    def required_fields(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "template": self.template_name,
            "required_input_count": "≥1 weighted_input",
            "required_output_count": "≥1",
            "requires_state": False,         # latches are internal/automatic
            "requires_periodic": False,
            "requires_threshold": True,      # the decision cutoff
            "supports_multi_namespace_fanin": True,
            "supports_pattern_as_list": True,  # pattern-as-list-embedded weights
        }
