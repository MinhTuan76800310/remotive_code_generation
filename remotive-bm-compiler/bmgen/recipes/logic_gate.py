"""LogicGate recipes — combine multiple input signals with a boolean operator.

These four recipes (AND, OR, XOR, NOT) read one or more signals from a single
triggering CAN frame and write a 0/1 result to one or more output signals.

Pattern:
- Read: a = frame.signals["Logic.A"], b = frame.signals["Logic.B"], ...
- Compute: result = a AND/OR/XOR b ...   (NOT takes a single input)
- Write: await namespace.restbus.update_signals(("Out", <0 or 1>), ...)

Arity (decided for this project):
- NOT  → exactly 1 input
- AND/OR/XOR → 2 or more inputs (N-ary)
- XOR over N inputs means "an odd number of inputs are true"

All four are stateless: the output depends only on the current frame's signals,
so no StateIR / reset handler is involved. This keeps them the simplest possible
multi-input recipe and fits the one-frame-per-handler model (a handler fires on a
single FrameFilter, so every input must live in that same frame).
"""

from __future__ import annotations

from bmgen.ir.model import HandlerIR
from bmgen.recipes.base import Recipe, RecipeContext

# Supported boolean operators and their human-readable descriptions.
_LOGIC_OPS = {
    "and": ("LogicAnd", "logical AND of two or more input signals"),
    "or": ("LogicOr", "logical OR of two or more input signals"),
    "xor": ("LogicXor", "logical XOR (odd number true) of two or more input signals"),
    "not": ("LogicNot", "logical NOT (inversion) of a single input signal"),
}


class LogicGateRecipe(Recipe):
    """Recipe for stateless boolean logic gates over input signals.

    One class parameterized by operator, instantiated four times (and/or/xor/not)
    in the registry. This keeps the four gates' shared structure in one place;
    only the value expression differs between them.
    """

    def __init__(self, op: str):
        if op not in _LOGIC_OPS:
            raise ValueError(f"Unknown logic op '{op}', expected one of {sorted(_LOGIC_OPS)}")
        self._op = op
        self._name, self._description = _LOGIC_OPS[op]

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def template_name(self) -> str:
        return "handler_logic.py.j2"

    def validate(self, handler_ir: HandlerIR) -> list[str]:
        """Validate input/output arity for this gate.

        - NOT requires exactly 1 input signal.
        - AND/OR/XOR require 2 or more input signals (N-ary).
        - All require at least 1 output signal and no state / periodic task.
        """
        errors = []
        n_inputs = len(handler_ir.input_signals)

        if self._op == "not":
            if n_inputs != 1:
                errors.append(
                    f"{self._name} requires exactly 1 input signal, found {n_inputs}"
                )
        else:
            if n_inputs < 2:
                errors.append(
                    f"{self._name} requires at least 2 input signals, found {n_inputs}"
                )

        if len(handler_ir.output_signals) < 1:
            errors.append(
                f"{self._name} requires at least 1 output signal, "
                f"found {len(handler_ir.output_signals)}"
            )

        if handler_ir.state is not None:
            errors.append(
                f"{self._name} is stateless but state '{handler_ir.state.name}' was declared"
            )

        if handler_ir.periodic_task is not None:
            errors.append(f"{self._name} is stateless but a periodic_task was declared")

        return errors

    def output_value_expr(self, handler_ir: HandlerIR) -> str:
        """Build the Python expression that computes this gate's 0/1 output.

        Each input variable holds a CAN signal value (0.0 / 1.0), which is
        already truthy/falsy in Python, so `bool(v)` makes the intent explicit
        without changing behavior. The result is normalized to a 0/1 integer
        (project decision) rather than a raw bool.

        - and: all inputs true       → 1 if (a and b and ...) else 0
        - or:  any input true        → 1 if (a or b or ...) else 0
        - xor: odd number true       → sum of truthy inputs is odd
        - not: invert the one input  → 1 if not a else 0
        """
        input_vars = [s.python_var_name for s in handler_ir.input_signals]

        if self._op == "not":
            return f"1 if not {input_vars[0]} else 0"

        if self._op == "xor":
            # N-ary XOR == "an odd number of inputs are true". Count truthy
            # inputs and test parity; works for any arity >= 2.
            counted = " + ".join(f"bool({v})" for v in input_vars)
            return f"1 if ({counted}) % 2 == 1 else 0"

        # and / or: join the inputs with the matching Python boolean keyword.
        joined = f" {self._op} ".join(input_vars)
        return f"1 if ({joined}) else 0"

    def build_context(self, handler_ir: HandlerIR) -> RecipeContext:
        """Build template context for a logic gate handler.

        Provides:
        - handler_name: method name
        - input_tuples: list of (signal_ref, python_var_name) to read each input
        - output_tuples: list of (signal_name, value_expr) — value_expr is the
          shared gate result, already filled by builder._apply_value_exprs
        - output_namespace_var: filled in by context_builder
        """
        input_tuples = [(s.name, s.python_var_name) for s in handler_ir.input_signals]
        output_tuples = [(s.name, s.value_expr) for s in handler_ir.output_signals]

        return RecipeContext(
            handler_name=handler_ir.name,
            pattern=self.name,
            template_name=self.template_name,
            context={
                "handler_name": handler_ir.name,
                "input_tuples": input_tuples,
                "output_tuples": output_tuples,
                "output_namespace_var": "",
            },
        )

    def required_fields(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "template": self.template_name,
            "required_input_count": 1 if self._op == "not" else "≥2",
            "required_output_count": "≥1",
            "requires_state": False,
            "requires_periodic": False,
        }
