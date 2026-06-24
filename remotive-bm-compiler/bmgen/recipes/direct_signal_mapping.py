"""DirectSignalMapping recipe — read one signal, forward same value to outputs.

This is the simplest behavioral model pattern, matching the getting_started
BCM example where a hazard light button signal is forwarded to both left and
right turn light request signals via restbus.update_signals.

Pattern:
- Read: frame.signals["Frame.Signal"] → extract value
- Write: await namespace.restbus.update_signals(
    ("OutputSignal1", value),
    ("OutputSignal2", value),
    ...
)
"""

from __future__ import annotations

from bmgen.ir.model import HandlerIR
from bmgen.recipes.base import Recipe, RecipeContext


class DirectSignalMappingRecipe(Recipe):
    """Recipe for direct signal forwarding: input → same value → multiple outputs."""

    @property
    def name(self) -> str:
        return "DirectSignalMapping"

    @property
    def description(self) -> str:
        return "Read one input signal and forward the same value to one or more output signals via restbus.update_signals"

    @property
    def template_name(self) -> str:
        return "handler_direct.py.j2"

    def validate(self, handler_ir: HandlerIR) -> list[str]:
        """Validate that the handler IR matches DirectSignalMapping requirements.

        Requirements:
        - Exactly 1 input signal
        - At least 1 output signal
        - No state variable
        - No periodic task
        """
        errors = []

        if len(handler_ir.input_signals) != 1:
            errors.append(
                f"DirectSignalMapping requires exactly 1 input signal, "
                f"found {len(handler_ir.input_signals)}"
            )

        flat_output_signals = [
            sig for g in handler_ir.output_groups for sig in g.signals
        ]
        if len(flat_output_signals) < 1:
            errors.append(
                f"DirectSignalMapping requires at least 1 output signal, "
                f"found {len(flat_output_signals)}"
            )

        if handler_ir.state is not None:
            errors.append(
                f"DirectSignalMapping does not require state, "
                f"but state '{handler_ir.state.name}' was declared"
            )

        if handler_ir.periodic_task is not None:
            errors.append(
                f"DirectSignalMapping does not require periodic_task, "
                f"but periodic_task was declared"
            )

        return errors

    def build_context(self, handler_ir: HandlerIR) -> RecipeContext:
        """Build template context for DirectSignalMapping handler.

        The context provides:
        - handler_name: Method name (e.g., "on_hazard_light")
        - input_signal_var: Snake_case variable name for the input signal value
        - input_signal_ref: Remotive signal reference string (e.g., "HazardLightButton.HazardLightButton")
        - output_tuples: List of (signal_name, value_expr) for restbus.update_signals
        - output_namespace_var: Python variable name for the output namespace
        """
        input_signal = handler_ir.input_signals[0]
        input_var = input_signal.python_var_name
        input_ref = input_signal.name

        # Build output tuples: (signal_name, value_expr) — flattened across all
        # output_groups. Multi-output fan-out is handled by the inline template
        # branch on `output_groups|length > 1`, not here.
        output_tuples = [
            (s.name, s.value_expr)
            for g in handler_ir.output_groups
            for s in g.signals
        ]

        # Find the output namespace Python variable name
        # This will be resolved by the context_builder which has access to the full IR
        output_ns_var = ""  # Will be filled in by context_builder

        return RecipeContext(
            handler_name=handler_ir.name,
            pattern=self.name,
            template_name=self.template_name,
            context={
                "handler_name": handler_ir.name,
                "input_signal_var": input_var,
                "input_signal_ref": input_ref,
                "output_tuples": output_tuples,
                "output_namespace_var": output_ns_var,
            },
        )

    def required_fields(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "template": self.template_name,
            "required_input_count": 1,
            "required_output_count": "≥1",
            "requires_state": False,
            "requires_periodic": False,
        }
