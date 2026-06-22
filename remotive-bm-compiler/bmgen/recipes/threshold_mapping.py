"""ThresholdMapping recipe — compare analog input against a threshold, output 0/1 boolean.

This recipe reads a single analog (float) input signal, compares it against a
configurable threshold value using a configurable operator, and outputs 1/0
(true/false) depending on a configurable direction. This is used for sensor
normalization where a raw analog value needs to be converted to a boolean
detection flag.

Pattern (defaults: operator '>', true_when 'above'):
- Read: weight_signal = frame.signals["SeatWeightSensor.WeightValue"]
- Compute: result = 1 if weight_signal > threshold else 0
- Write: await namespace.restbus.update_signals(("CPDSeatData.SeatWeightDetected", result), ...)

YAML fields in the handler spec:
  threshold: 5.0            # required float — the comparison value
  operator: ">"             # optional — one of >, >=, <, <=, ==, != (default '>')
  true_when: above          # optional — 'above' (default) | 'below'
                            #   above → 1 if (input op threshold) else 0
                            #   below → 1 if not (input op threshold) else 0

⚠️ YAML QUOTING REQUIREMENT — operator MUST be YAML-quoted:
  operator: ">="            # ✓ quoted — parses to the string ">="
  operator: >=              # ✗ UNQUOTED — `>` is YAML's folded-block-scalar
                            #   indicator, so this raises yaml.YAMLError at PARSE
                            #   time (before any ThresholdMapping validation runs).
                            #   Always quote operator values: ">=", "<=", "==", etc.
                            # Omitting operator entirely is also valid and yields
                            # the default '>'.

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

# Allowed comparison operators for ThresholdMapping. Kept as a small closed set
# so a typo like `=>` is rejected close to the YAML (in validate / output_value_expr)
# rather than producing a Python syntax error only at generated-code compile time.
#
# NOTE: in YAML the operator value MUST be quoted (operator: ">=") because `>` and
# `|` are block-scalar indicators — an unquoted operator: >= raises yaml.YAMLError
# at parse time, before any validation here can run. See the module docstring.
_VALID_OPERATORS = frozenset({">", ">=", "<", "<=", "==", "!="})
_VALID_TRUE_WHEN = frozenset({"above", "below"})
_DEFAULT_OPERATOR = ">"
_DEFAULT_TRUE_WHEN = "above"


class ThresholdMappingRecipe(Recipe):
    """Recipe for threshold-based analog-to-boolean conversion.

    Reads a single float input, compares it against a threshold value using a
    configurable operator, and outputs 1 (true) or 0 (false) depending on the
    configured direction.

    Defaults (operator `>`, true_when `above`) reproduce the original behavior
    exactly: `1 if input > threshold else 0`. Existing specs that omit
    `operator:` / `true_when:` therefore render byte-identically.
    """

    @property
    def name(self) -> str:
        return "ThresholdMapping"

    @property
    def description(self) -> str:
        return (
            "Compare a single analog input against a threshold; output 1 when the "
            "comparison holds (true_when: above, default) or when it does NOT hold "
            "(true_when: below). operator defaults to '>'"
        )

    @property
    def template_name(self) -> str:
        return "handler_direct.py.j2"

    def _resolved_operator(self, handler_ir: HandlerIR) -> str:
        return handler_ir.operator if handler_ir.operator is not None else _DEFAULT_OPERATOR

    def _resolved_true_when(self, handler_ir: HandlerIR) -> str:
        return handler_ir.true_when if handler_ir.true_when is not None else _DEFAULT_TRUE_WHEN

    def validate(self, handler_ir: HandlerIR) -> list[str]:
        """Validate that the handler IR matches ThresholdMapping requirements.

        Requirements:
        - Exactly 1 input signal (the analog value)
        - At least 1 output signal (the boolean result)
        - No state variable (stateless comparison)
        - No periodic task
        - threshold value must be set
        - operator (if given) must be one of >, >=, <, <=, ==, !=
        - true_when (if given) must be one of above, below
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

        if handler_ir.operator is not None and handler_ir.operator not in _VALID_OPERATORS:
            errors.append(
                f"ThresholdMapping 'operator' must be one of "
                f"{sorted(_VALID_OPERATORS)}, got {handler_ir.operator!r}"
            )

        if handler_ir.true_when is not None and handler_ir.true_when not in _VALID_TRUE_WHEN:
            errors.append(
                f"ThresholdMapping 'true_when' must be one of "
                f"{sorted(_VALID_TRUE_WHEN)}, got {handler_ir.true_when!r}"
            )

        return errors

    def output_value_expr(self, handler_ir: HandlerIR) -> str:
        """Return the Python expression for the threshold comparison.

        - true_when above (default): `1 if {input} {op} {thr} else 0`
        - true_when below          : `1 if not ({input} {op} {thr}) else 0`

        Bad operator/true_when values raise ValueError (defence in depth: validate()
        already rejects them, but a caller that invokes output_value_expr directly
        — e.g. _apply_value_exprs via build_ir, which runs the IR validator but not
        recipe.validate — must still fail loudly instead of emitting broken Python).
        """
        input_var = handler_ir.input_signals[0].python_var_name
        threshold = handler_ir.threshold
        op = self._resolved_operator(handler_ir)
        direction = self._resolved_true_when(handler_ir)

        if op not in _VALID_OPERATORS:
            raise ValueError(
                f"ThresholdMapping 'operator' must be one of "
                f"{sorted(_VALID_OPERATORS)}, got {op!r}"
            )
        if direction not in _VALID_TRUE_WHEN:
            raise ValueError(
                f"ThresholdMapping 'true_when' must be one of "
                f"{sorted(_VALID_TRUE_WHEN)}, got {direction!r}"
            )

        comparison = f"{input_var} {op} {threshold}"
        if direction == "below":
            return f"1 if not ({comparison}) else 0"
        return f"1 if {comparison} else 0"

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
            "optional_operator": sorted(_VALID_OPERATORS),
            "optional_true_when": sorted(_VALID_TRUE_WHEN),
            # `>` / `|` are YAML block-scalar indicators, so operator values MUST
            # be quoted in the YAML (operator: ">=") or parsing raises yaml.YAMLError
            # before validation runs. Surfaced here so `bmgen recipes` warns users.
            "operator_must_be_yaml_quoted": True,
        }
