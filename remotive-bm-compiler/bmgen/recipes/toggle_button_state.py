"""ToggleButtonState recipe — read button, toggle boolean state, write state to outputs.

Pattern:
- Read: frame.signals["Frame.Signal"] → extract button value
- If button pressed (value != 0 and previous state was off):
  - Toggle internal boolean state: self._state_name = not self._state_name
- Write: await namespace.restbus.update_signals(
    ("OutputSignal1", 1 if self._state_name else 0),
    ("OutputSignal2", 1 if self._state_name else 0),
)

This matches the hazard button pattern in the full BCM example:
  - Press once → hazard_enabled = True → both turn lights ON
  - Press again → hazard_enabled = False → both turn lights OFF

The generated handler tracks the previous button state to detect "presses"
(transition from 0 to non-zero), not continuous holding.
"""

from __future__ import annotations

from bmgen.ir.model import HandlerIR
from bmgen.recipes.base import Recipe, RecipeContext


class ToggleButtonStateRecipe(Recipe):
    """Recipe for toggle button: press → toggle boolean → write state to outputs."""

    @property
    def name(self) -> str:
        return "ToggleButtonState"

    @property
    def description(self) -> str:
        return "Read a button signal, toggle an internal boolean state, and write the state to output signals"

    @property
    def template_name(self) -> str:
        return "handler_toggle.py.j2"

    def validate(self, handler_ir: HandlerIR) -> list[str]:
        """Validate that the handler IR matches ToggleButtonState requirements.

        Requirements:
        - Exactly 1 input signal
        - At least 1 output signal
        - State variable with type='bool'
        - State has reset_value
        """
        errors = []

        if len(handler_ir.input_signals) != 1:
            errors.append(
                f"ToggleButtonState requires exactly 1 input signal, "
                f"found {len(handler_ir.input_signals)}"
            )

        if len(handler_ir.output_signals) < 1:
            errors.append(
                f"ToggleButtonState requires at least 1 output signal, "
                f"found {len(handler_ir.output_signals)}"
            )

        if handler_ir.state is None:
            errors.append(
                f"ToggleButtonState requires a state variable, "
                f"but no state was declared"
            )
        else:
            if handler_ir.state.type != "bool":
                errors.append(
                    f"ToggleButtonState requires state type 'bool', "
                    f"found '{handler_ir.state.type}'"
                )

            if handler_ir.state.reset_value is None:
                errors.append(
                    f"ToggleButtonState requires state with reset_value, "
                    f"but state '{handler_ir.state.name}' has no reset_value"
                )

        return errors

    def build_context(self, handler_ir: HandlerIR) -> RecipeContext:
        """Build template context for ToggleButtonState handler.

        The context provides:
        - handler_name: Method name
        - input_signal_var: Snake_case variable name for input
        - input_signal_ref: Remotive signal reference string
        - state_name: Internal state variable name (e.g., "hazard_enabled")
        - state_initial: Initial value (e.g., False)
        - state_reset_value: Reset value (e.g., False)
        - output_tuples: List of (signal_name, value_expr)
        - previous_state_var: Variable name for tracking previous button state
        """
        input_signal = handler_ir.input_signals[0]
        state = handler_ir.state

        # Build output tuples
        output_tuples = [(s.name, s.value_expr) for s in handler_ir.output_signals]

        # Previous state variable tracks the last known button value to detect "press"
        previous_state_var = f"_previous_{state.name}"

        return RecipeContext(
            handler_name=handler_ir.name,
            pattern=self.name,
            template_name=self.template_name,
            context={
                "handler_name": handler_ir.name,
                "input_signal_var": input_signal.python_var_name,
                "input_signal_ref": input_signal.name,
                "state_name": state.name,
                "state_initial": state.initial,
                "state_reset_value": state.reset_value,
                "state_private_var": f"_{state.name}",
                "previous_state_var": previous_state_var,
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
            "requires_state": True,
            "requires_state_type": "bool",
            "requires_periodic": False,
        }
