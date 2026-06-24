"""PeriodicBlinkingOutput recipe — state enables/disables blinking, periodic async task.

Pattern:
- Read: frame.signals["Frame.Signal"] → detect enable/disable
- If input indicates enable: self._state = True, start_ticker()
- If input indicates disable: self._state = False, stop_ticker()
- Periodic ticker toggles output signals on/off at fixed interval
- Cleanup: cancel ticker on model exit/reboot

This matches the turn signal blinking pattern in the full BCM example,
using the `create_ticker` API from remotivelabs.topology.time.async_ticker.
"""

from __future__ import annotations

from bmgen.ir.model import HandlerIR
from bmgen.recipes.base import Recipe, RecipeContext


class PeriodicBlinkingOutputRecipe(Recipe):
    """Recipe for periodic blinking: state controls ticker, ticker toggles outputs."""

    @property
    def name(self) -> str:
        return "PeriodicBlinkingOutput"

    @property
    def description(self) -> str:
        return "Use internal state to enable/disable blinking, generate periodic async task, with cleanup and reset behavior"

    @property
    def template_name(self) -> str:
        return "handler_blink.py.j2"

    def validate(self, handler_ir: HandlerIR) -> list[str]:
        """Validate that the handler IR matches PeriodicBlinkingOutput requirements.

        Requirements:
        - Exactly 1 input signal
        - At least 1 output signal
        - State variable with type='bool' and reset_value
        - Periodic task with cleanup=True
        """
        errors = []

        if len(handler_ir.input_signals) != 1:
            errors.append(
                f"PeriodicBlinkingOutput requires exactly 1 input signal, "
                f"found {len(handler_ir.input_signals)}"
            )

        flat_output_signals = [
            sig for g in handler_ir.output_groups for sig in g.signals
        ]
        if len(flat_output_signals) < 1:
            errors.append(
                f"PeriodicBlinkingOutput requires at least 1 output signal, "
                f"found {len(flat_output_signals)}"
            )

        if handler_ir.state is None:
            errors.append(
                f"PeriodicBlinkingOutput requires a state variable, "
                f"but no state was declared"
            )
        else:
            if handler_ir.state.type != "bool":
                errors.append(
                    f"PeriodicBlinkingOutput requires state type 'bool', "
                    f"found '{handler_ir.state.type}'"
                )

            if handler_ir.state.reset_value is None:
                errors.append(
                    f"PeriodicBlinkingOutput requires state with reset_value, "
                    f"but state '{handler_ir.state.name}' has no reset_value"
                )

        if handler_ir.periodic_task is None:
            errors.append(
                f"PeriodicBlinkingOutput requires a periodic_task, "
                f"but no periodic_task was declared"
            )
        else:
            if not handler_ir.periodic_task.cleanup:
                errors.append(
                    f"PeriodicBlinkingOutput requires periodic_task.cleanup=True, "
                    f"found cleanup={handler_ir.periodic_task.cleanup}"
                )

        return errors

    def build_context(self, handler_ir: HandlerIR) -> RecipeContext:
        """Build template context for PeriodicBlinkingOutput handler.

        The context provides:
        - handler_name: Method name
        - input_signal_var/input_signal_ref: Input signal details
        - state_name/state_initial/state_reset_value: State variable details
        - ticker_interval: Blink interval in seconds
        - blink_output_signals: Signals to toggle on/off
        - blink_output_namespace_var: Namespace for blink signals
        - ticker_var_name: Asyncio.Task variable name for the ticker
        """
        input_signal = handler_ir.input_signals[0]
        state = handler_ir.state
        periodic = handler_ir.periodic_task

        # Build output tuples for the handler (enable/disable state, flattened).
        output_tuples = [
            (s.name, s.value_expr)
            for g in handler_ir.output_groups
            for s in g.signals
        ]


# Type hint for HandlerIR — keeps existing imports working        # Build blink output signal names for the periodic task
        blink_signal_names = periodic.blink_output_signals if periodic else []

        # Ticker variable name
        ticker_var_name = f"_ticker_{state.name}" if state else "_ticker"

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
                "ticker_interval": periodic.interval_sec if periodic else 1.0,
                "ticker_var_name": ticker_var_name,
                "blink_output_signals": blink_signal_names,
                "blink_output_namespace_var": "",
                "output_tuples": output_tuples,
                "output_namespace_var": "",
            },
        )

    def output_value_expr(self, handler_ir: HandlerIR) -> str:
        """Output reflects the blink-enabled boolean state as 0/1."""
        state_name = handler_ir.state.name if handler_ir.state else "blink_enabled"
        return f"1 if self._{state_name} else 0"

    def required_fields(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "template": self.template_name,
            "required_input_count": 1,
            "required_output_count": "≥1",
            "requires_state": True,
            "requires_state_type": "bool",
            "requires_periodic": True,
            "requires_periodic_cleanup": True,
        }
