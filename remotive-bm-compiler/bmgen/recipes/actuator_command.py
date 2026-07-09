"""ActuatorCommand recipe — edge-triggered status publish on command change.

Pattern (matches the hand-written SE on_seat_cmd simulate path):
- Read: cast(frame.signals["Frame.Signal"]) → current command
- Compare: if current != self._last_<handler>:
    - self._last_<handler> = current
    - Write: await ns.restbus.update_signals(("Status.Done", 1), ...)
- Else: no-op (no bus spam)

YAML (list-form pattern, same style as ThresholdMapping):
  handlers:
    - name: on_seat_cmd
      pattern:
        - name: ActuatorCommand
          value_type: int          # optional — int|float|bool|str (default int)
          initial_state: -1        # optional — last-seen sentinel (default -1 for int)
      input:
        namespace: SE-BodyCAN
        signal: PW_SeatCmd.SeatPosTarget
      output:
        - namespace: SE-BodyCAN
          signals: [PW_SeatStatus.SeatDone]

State is auto-synthesised by the IR builder from pattern_params (no explicit
`state:` block required in the SWC). Output on edge is always 1 (True/done);
there is no publish_value knob.
"""

from __future__ import annotations

from bmgen.ir.model import HandlerIR
from bmgen.recipes.base import Recipe, RecipeContext

_VALID_VALUE_TYPES = frozenset({"int", "float", "bool", "str"})
_DEFAULT_VALUE_TYPE = "int"
_DEFAULT_INITIAL_BY_TYPE = {
    "int": -1,
    "float": -1.0,
    "bool": False,
    "str": "",
}


class ActuatorCommandRecipe(Recipe):
    """Recipe for edge-triggered actuator command → status(1) publish."""

    @property
    def name(self) -> str:
        return "ActuatorCommand"

    @property
    def description(self) -> str:
        return (
            "On command change (vs last-seen), publish status signals as 1 (True/done). "
            "Stateful edge detector for simulated actuator 'done' notification."
        )

    @property
    def template_name(self) -> str:
        return "handler_actuator_command.py.j2"

    def _resolved_value_type(self, handler_ir: HandlerIR) -> str:
        vt = handler_ir.pattern_params.get("value_type", _DEFAULT_VALUE_TYPE)
        return vt if vt in _VALID_VALUE_TYPES else _DEFAULT_VALUE_TYPE

    def validate(self, handler_ir: HandlerIR) -> list[str]:
        """Validate ActuatorCommand structural requirements.

        Requirements:
        - Exactly 1 input signal (the command)
        - At least 1 output signal (the status/done flag)
        - State variable present (builder auto-synthesises it)
        - value_type (if given) must be int|float|bool|str
        - No periodic task
        """
        errors: list[str] = []

        flat_output_signals = [
            sig for g in handler_ir.output_groups for sig in g.signals
        ]

        if len(handler_ir.input_signals) != 1:
            errors.append(
                f"ActuatorCommand requires exactly 1 input signal, "
                f"found {len(handler_ir.input_signals)}"
            )

        if len(flat_output_signals) < 1:
            errors.append(
                f"ActuatorCommand requires at least 1 output signal, "
                f"found {len(flat_output_signals)}"
            )

        if handler_ir.state is None:
            errors.append(
                "ActuatorCommand requires a state variable (auto-synthesised by "
                "builder from pattern_params; if missing, builder did not run)"
            )

        if handler_ir.periodic_task is not None:
            errors.append("ActuatorCommand does not support periodic_task")

        vt = handler_ir.pattern_params.get("value_type")
        if vt is not None and vt not in _VALID_VALUE_TYPES:
            errors.append(
                f"ActuatorCommand 'value_type' must be one of "
                f"{sorted(_VALID_VALUE_TYPES)}, got {vt!r}"
            )

        return errors

    def output_value_expr(self, handler_ir: HandlerIR) -> str:
        """On edge, always publish 1 (True / done)."""
        return "1"

    def build_context(self, handler_ir: HandlerIR) -> RecipeContext:
        """Build template context for the edge-detect handler body."""
        input_signal = handler_ir.input_signals[0]
        state = handler_ir.state
        value_type = self._resolved_value_type(handler_ir)

        output_tuples = [
            (s.name, s.value_expr)
            for g in handler_ir.output_groups
            for s in g.signals
        ]

        # Cast expression prefix/suffix for the frame.signals read.
        # int/float/bool wrap the read; str is a no-op cast.
        cast_prefix = f"{value_type}(" if value_type != "str" else ""
        cast_suffix = ")" if value_type != "str" else ""

        state_name = state.name if state is not None else f"last_{handler_ir.name}"
        state_private = f"_{state_name}"
        state_initial = state.initial if state is not None else _DEFAULT_INITIAL_BY_TYPE[value_type]

        return RecipeContext(
            handler_name=handler_ir.name,
            pattern=self.name,
            template_name=self.template_name,
            context={
                "handler_name": handler_ir.name,
                "input_signal_var": input_signal.python_var_name,
                "input_signal_ref": input_signal.name,
                "value_type": value_type,
                "cast_prefix": cast_prefix,
                "cast_suffix": cast_suffix,
                "state_name": state_name,
                "state_private_var": state_private,
                "state_initial": state_initial,
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
            "state_auto_synthesised": True,
            "optional_value_type": sorted(_VALID_VALUE_TYPES),
            "optional_initial_state": "typed sentinel (default -1 for int)",
            "publish_on_edge": 1,
        }
