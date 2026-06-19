"""ThresholdMapping recipe — compare analog input against a threshold, output 0/1 boolean.

This recipe reads a single analog (float) input signal, compares it against
a configurable threshold value, and outputs 1 if the input exceeds the
threshold or 0 otherwise. This is used for sensor normalization where a
raw analog value needs to be converted to a boolean detection flag.

Pattern:
- Read: weight_signal = frame.signals["SeatWeightSensor.WeightValue"]
- Compute: result = 1 if weight_signal > threshold else 0
- Write: await namespace.restbus.update_signals(("CPDSeatData.SeatWeightDetected", result), ...)

The threshold value is specified in the YAML handler spec as:
  threshold: 5.0

This recipe requires:
- Exactly 1 input signal (the analog value to compare)
- At least 1 output signal (the boolean result)
- No state variable (stateless comparison)
- No periodic task
- A threshold float value in the handler spec
"""

from __future__ import annotations

from bmgen.ir.model import HandlerIR
from bmgen.recipes.base import Recipe, RecipeContext


class ThresholdMappingRecipe(Recipe):
    """Recipe for threshold-based analog-to-boolean conversion.

    Reads a single float input, compares it against a threshold value,
    and outputs 1 (true) if input > threshold, else 0 (false).
    """

    @property
    def name(self) -> str:
        return "ThresholdMapping"

    @property
    def description(self) -> str:
        return "Compare a single analog input against a threshold value; output 1 if input > threshold, else 0"

    @property
    def template_name(self) -> str:
        return "handler_direct.py.j2"

    def validate(self, handler_ir: HandlerIR) -> list[str]:
        """Validate that the handler IR matches ThresholdMapping requirements.

        Requirements:
        - Exactly 1 input signal (the analog value)
        - At least 1 output signal (the boolean result)
        - No state variable (stateless comparison)
        - No periodic task
        - threshold value must be set
        """
        errors = []

        if len(handler_ir.input_signals) != 1:
            errors.append(
                f"ThresholdMapping requires exactly 1 input signal, "
                f"found {len(handler_ir.input_signals)}"
            )

        if len(handler_ir.output_signals) < 1:
            errors.append(
                f"ThresholdMapping requires at least 1 output signal, "
                f"found {len(handler_ir.output_signals)}"
            )

        if handler_ir.state is not None:
            errors.append(
                f"ThresholdMapping is stateless but state '{handler_ir.state.name}' was declared"
            )

        if handler_ir.periodic_task is not None:
            errors.append(f"ThresholdMapping is stateless but a periodic_task was declared")

        if handler_ir.threshold is None:
            errors.append(
                f"ThresholdMapping requires a threshold value in the handler spec "
                f"(e.g., threshold: 5.0)"
            )

        return errors

    def output_value_expr(self, handler_ir: HandlerIR) -> str:
        """Return the Python expression for threshold comparison.

        Generates: 1 if {input_var} > {threshold} else 0
        """
        input_var = handler_ir.input_signals[0].python_var_name
        threshold = handler_ir.threshold
        return f"1 if {input_var} > {threshold} else 0"

    def build_context(self, handler_ir: HandlerIR) -> RecipeContext:
        """Build template context for ThresholdMapping handler.

        Uses the same handler_direct.py.j2 template as DirectSignalMapping
        since the generated code structure is identical — just the value_expr
        differs (threshold comparison vs. direct forwarding).
        """
        input_signal = handler_ir.input_signals[0]
        input_var = input_signal.python_var_name
        input_ref = input_signal.name

        output_tuples = [(s.name, s.value_expr) for s in handler_ir.output_signals]

        return RecipeContext(
            handler_name=handler_ir.name,
            pattern=self.name,
            template_name=self.template_name,
            context={
                "handler_name": handler_ir.name,
                "input_signal_var": input_var,
                "input_signal_ref": input_ref,
                "output_tuples": output_tuples,
                "output_namespace_var": "",
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
            "requires_threshold": True,
        }
