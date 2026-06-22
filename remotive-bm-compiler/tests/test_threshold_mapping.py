"""Tests for the ThresholdMapping recipe — threshold comparison with configurable
operator and direction.

These tests pin down four behaviors:
1. BACKWARD COMPATIBILITY — the pre-existing default (operator `>`, true_when
   `above`) must render byte-identical to the original `1 if x > thr else 0`.
   This guards examples/cpd/subecu_seat.yaml, which CI does NOT run.
2. GENERALIZATION — operator (`>=`,`<`,`<=`,`==`,`!=`) and true_when
   (`above`/`below`) produce the correct comparison expression.
3. VALIDATION — malformed operator / true_when are rejected close to the YAML
   (not at generated-code compile time), with the echoed bad value + rule id.
4. GENERATION — the value_expr reaches the rendered __main__.py UNQUOTED inside
   the output tuple (closes the value_expr→template rendering gap; a template
   regression that quoted value_expr as a string literal would be caught).
"""

from __future__ import annotations

import ast
import os

import pytest

from bmgen.compiler.context_builder import build_template_context
from bmgen.compiler.python_generator import generate
from bmgen.ir.builder import build_ir, BuilderError
from bmgen.ir.model import HandlerIR, InputSignalIR, OutputSignalIR
from bmgen.ir.parser import parse_yaml_string
from bmgen.recipes.registry import create_default_registry
from bmgen.recipes.threshold_mapping import ThresholdMappingRecipe


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

# A minimal valid ThresholdMapping model. Tests override the handler's
# threshold / operator / true_when to exercise each case.
_BASE_THRESHOLD_YAML = """
model:
  name: SeatECU
  ecu_name: SEAT

namespaces:
  - name: SEAT-LocalSensorCan0
    type: can
    role: input
  - name: SEAT-SeatCan0
    type: can
    role: output
    restbus:
      sender_filter: SEAT

handlers:
  - name: on_seat_occupancy
    pattern: ThresholdMapping
    threshold: 8.0
    input:
      namespace: SEAT-LocalSensorCan0
      frame_filter: SeatWeightSensor
      signal: SeatWeightSensor.WeightKg
    output:
      namespace: SEAT-SeatCan0
      signals:
        - ChildDetectionInput.SeatOccupied
"""


def _threshold_handler_spec(**overrides) -> str:
    """Return a YAML spec with the threshold handler fields overridden.

    Accepts threshold / operator / true_when overrides applied into the handler.
    """
    handler_lines = [
        "  - name: on_seat_occupancy",
        "    pattern: ThresholdMapping",
        f"    threshold: {overrides.get('threshold', 8.0)}",
    ]
    if "operator" in overrides:
        handler_lines.append(f"    operator: {overrides['operator']!r}")
    if "true_when" in overrides:
        handler_lines.append(f"    true_when: {overrides['true_when']}")
    handler_lines += [
        "    input:",
        "      namespace: SEAT-LocalSensorCan0",
        "      frame_filter: SeatWeightSensor",
        "      signal: SeatWeightSensor.WeightKg",
        "    output:",
        "      namespace: SEAT-SeatCan0",
        "      signals:",
        "        - ChildDetectionInput.SeatOccupied",
    ]
    return _BASE_THRESHOLD_YAML.replace(
        "  - name: on_seat_occupancy\n    pattern: ThresholdMapping\n    threshold: 8.0\n",
        "\n".join(handler_lines) + "\n",
    )


def _value_expr_for(**overrides) -> str:
    """Build the IR for the given threshold handler overrides and return the
    single output signal's value_expr (the generated comparison expression)."""
    spec = parse_yaml_string(_threshold_handler_spec(**overrides))
    ir = build_ir(spec)
    handler = ir.handlers[0]
    assert handler.output_signals, "ThresholdMapping handler must have outputs"
    return handler.output_signals[0].value_expr


def _make_handler_ir(
    threshold: float = 8.0,
    operator: str | None = None,
    true_when: str | None = None,
) -> HandlerIR:
    """Construct a HandlerIR directly (unit-level, no YAML round-trip)."""
    return HandlerIR(
        name="on_seat_occupancy",
        pattern="ThresholdMapping",
        input_namespace="SEAT-LocalSensorCan0",
        input_frame_filter="SeatWeightSensor",
        input_signals=[InputSignalIR(name="SeatWeightSensor.WeightKg",
                                     python_var_name="weight_kg")],
        output_namespace="SEAT-SeatCan0",
        output_signals=[OutputSignalIR(name="ChildDetectionInput.SeatOccupied")],
        threshold=threshold,
        operator=operator,
        true_when=true_when,
    )


# ---------------------------------------------------------------------------
# 1. Backward compatibility — default must be byte-identical to the original
# ---------------------------------------------------------------------------

# The input signal SeatWeightSensor.WeightKg derives to the Python var
# `seat_weight_sensor_signal` (frame name → snake_case + "_signal"), per
# _derive_signal_var_name in bmgen/ir/model.py. YAML-path tests must assert
# the REAL derived name, not a made-up one.
VAR = "seat_weight_sensor_signal"


class TestThresholdMappingBackwardCompat:
    """The pre-generalization behavior must not change for existing YAML."""

    def test_default_renders_gt_above(self):
        """No operator/true_when → `1 if x > thr else 0` (the original form)."""
        expr = _value_expr_for(threshold=5.0)
        assert expr == f"1 if {VAR} > 5.0 else 0"

    def test_subecu_seat_example_unchanged(self):
        """examples/cpd/subecu_seat.yaml uses threshold: 5.0 with no operator.
        Its generated expression must stay `1 if seat_weight_sensor_signal > 5.0 else 0`."""
        expr = _value_expr_for(threshold=5.0)
        # Structural form unchanged: `>`, no negation, else 0.
        assert expr == f"1 if {VAR} > 5.0 else 0"
        assert "not " not in expr  # default direction is above, no negation


# ---------------------------------------------------------------------------
# 2. Generalization — operator + true_when
# ---------------------------------------------------------------------------

class TestThresholdMappingOperator:
    """Each operator produces the correct comparison token in the expression."""

    @pytest.mark.parametrize("operator,token", [
        (">", ">"),
        (">=", ">="),
        ("<", "<"),
        ("<=", "<="),
        ("==", "=="),
        ("!=", "!="),
    ])
    def test_operator_appears_in_expr(self, operator, token):
        expr = _value_expr_for(threshold=8.0, operator=operator)
        # default true_when=above → no negation, token appears directly
        assert token in expr
        assert "not " not in expr

    def test_above_default_no_negation(self):
        expr = _value_expr_for(threshold=8.0, operator=">=")
        assert expr == f"1 if {VAR} >= 8.0 else 0"

    def test_below_negates(self):
        """true_when: below → `1 if not (x op thr) else 0`."""
        expr = _value_expr_for(threshold=8.0, operator=">=", true_when="below")
        assert expr == f"1 if not ({VAR} >= 8.0) else 0"

    def test_below_with_lt(self):
        expr = _value_expr_for(threshold=8.0, operator="<", true_when="below")
        assert expr == f"1 if not ({VAR} < 8.0) else 0"


class TestThresholdMappingSeatEcuCase:
    """The SeatECU rule: SeatOccupied = False if weight_kg >= 8 else True.
    That is TRUE when BELOW 8kg → operator >=, true_when below."""

    def test_seat_occupied_true_below_8kg(self):
        expr = _value_expr_for(threshold=8.0, operator=">=", true_when="below")
        assert expr == f"1 if not ({VAR} >= 8.0) else 0"
        # Semantically: weight=5 → not(5>=8)=not False=True→1 (child present)
        #               weight=8 → not(8>=8)=not True=False→0 (no child)


# ---------------------------------------------------------------------------
# 3. Validation — bad operator / true_when rejected early
# ---------------------------------------------------------------------------

class TestThresholdMappingValidation:
    """Malformed operator/true_when must be rejected, not silently produce
    broken generated code."""

    # Clearly-invalid operators. (`>` is intentionally excluded — it is the
    # VALID default. The empty-string case is covered separately below.)
    @pytest.mark.parametrize("bad_operator", ["=>", "~", ">>", "greater"])
    def test_invalid_operator_rejected(self, bad_operator):
        spec = parse_yaml_string(
            _threshold_handler_spec(threshold=8.0, operator=bad_operator)
        )
        with pytest.raises(BuilderError) as exc:
            build_ir(spec)
        # Tight assertions (not a tautology): the bad value must be ECHOED in the
        # message, and the correct NAMED RULE must be among the violations.
        msg = str(exc.value)
        assert bad_operator in msg, f"bad operator {bad_operator!r} not echoed in: {msg}"
        rules = [v.rule for v in exc.value.violations]
        assert "threshold_mapping_invalid_operator" in rules, (
            f"expected rule 'threshold_mapping_invalid_operator', got rules={rules}"
        )

    def test_empty_string_operator_rejected(self):
        """An explicit empty operator (operator: '') is not a valid operator and
        must be rejected — it is neither None (→ default '>') nor a real token."""
        spec = parse_yaml_string(
            _threshold_handler_spec(threshold=8.0, operator="")
        )
        with pytest.raises(BuilderError) as exc:
            build_ir(spec)
        rules = [v.rule for v in exc.value.violations]
        assert "threshold_mapping_invalid_operator" in rules

    @pytest.mark.parametrize("bad_true_when", ["under", "ABOVE", "low"])
    def test_invalid_true_when_rejected(self, bad_true_when):
        spec = parse_yaml_string(
            _threshold_handler_spec(threshold=8.0, true_when=bad_true_when)
        )
        with pytest.raises(BuilderError) as exc:
            build_ir(spec)
        # Tight assertions: the bad value must be echoed AND the correct named
        # rule fired (guards against a regression that reported the wrong field).
        msg = str(exc.value)
        assert bad_true_when in msg, f"bad true_when {bad_true_when!r} not echoed in: {msg}"
        rules = [v.rule for v in exc.value.violations]
        assert "threshold_mapping_invalid_true_when" in rules, (
            f"expected rule 'threshold_mapping_invalid_true_when', got rules={rules}"
        )

    def test_valid_operator_passes_validation(self):
        # No exception means accepted.
        expr = _value_expr_for(threshold=8.0, operator=">=")
        assert ">=" in expr


# ---------------------------------------------------------------------------
# 4. Registry / recipe unit-level
# ---------------------------------------------------------------------------

class TestThresholdMappingRecipe:
    def test_recipe_registered(self):
        registry = create_default_registry()
        recipe = registry.get("ThresholdMapping")
        assert recipe is not None
        assert isinstance(recipe, ThresholdMappingRecipe)

    def test_required_fields_advertises_new_options(self):
        recipe = ThresholdMappingRecipe()
        fields = recipe.required_fields()
        assert fields["requires_threshold"] is True
        # New optional fields should be advertised for discoverability.
        assert set(fields["optional_operator"]) == {">", ">=", "<", "<=", "==", "!="}
        assert set(fields["optional_true_when"]) == {"above", "below"}

    def test_validate_rejects_bad_operator_unit(self):
        recipe = ThresholdMappingRecipe()
        h = _make_handler_ir(operator="=>")
        errors = recipe.validate(h)
        assert any("operator" in e.lower() for e in errors)

    def test_validate_rejects_bad_true_when_unit(self):
        recipe = ThresholdMappingRecipe()
        h = _make_handler_ir(true_when="under")
        errors = recipe.validate(h)
        assert any("true_when" in e.lower() for e in errors)

    def test_validate_accepts_defaults(self):
        recipe = ThresholdMappingRecipe()
        h = _make_handler_ir()  # no operator/true_when → defaults
        errors = recipe.validate(h)
        assert errors == []


# ---------------------------------------------------------------------------
# 5. Full generation — value_expr must reach __main__.py UNQUOTED
#    (closes the value_expr→template rendering gap. A template regression that
#    quoted value_expr as a string literal would still be ast.parse-valid, so a
#    syntax check alone is insufficient — we assert the raw expression text.)
# ---------------------------------------------------------------------------

# A SeatECU-shaped spec with operator >=, true_when below (the inverted rule).
# Kept inline (not reading the real seat_ecu.yaml) so the test is self-contained
# and pins the generation path independent of the example file's location.
_SEAT_ECU_GEN_YAML = """
model:
  name: SeatECU
  ecu_name: SEAT

namespaces:
  - name: SEAT-LocalSensorCan0
    type: can
    role: input
  - name: SEAT-SeatCan0
    type: can
    role: output
    restbus:
      sender_filter: SEAT

handlers:
  - name: on_seat_occupancy
    pattern: ThresholdMapping
    threshold: 8.0
    operator: ">="
    true_when: below
    input:
      namespace: SEAT-LocalSensorCan0
      frame_filter: SeatWeightSensor
      signal: SeatWeightSensor.WeightKg
    output:
      namespace: SEAT-SeatCan0
      signals:
        - ChildDetectionInput.SeatOccupied
"""


class TestThresholdMappingGeneration:
    """End-to-end generation: the threshold expression reaches __main__.py
    as an UNQUOTED expression inside the restbus.update_signals tuple."""

    def test_generated_main_py_is_valid_python(self, temp_output_dir):
        spec = parse_yaml_string(_SEAT_ECU_GEN_YAML)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "seatecu", "__main__.py")
        assert os.path.isfile(main_path), f"expected {main_path} to be generated"
        with open(main_path) as f:
            content = f.read()
        ast.parse(content)  # must be syntactically valid Python

    def test_threshold_expression_rendered_unquoted(self, temp_output_dir):
        """The expression `1 if not (seat_weight_sensor_signal >= 8.0) else 0`
        must appear UNQUOTED in __main__.py — i.e. as a Python expression inside
        the output tuple, NOT as a string literal. A regression that quoted it
        as ("Signal", "1 if ... else 0") would break semantics but still parse,
        so we assert the raw expression substring is present."""
        spec = parse_yaml_string(_SEAT_ECU_GEN_YAML)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "seatecu", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        expected_expr = "1 if not (seat_weight_sensor_signal >= 8.0) else 0"
        assert expected_expr in content, (
            f"expected unquoted threshold expression in __main__.py, "
            f"got:\n{content}"
        )
        # It must be an expression (bare), not a quoted string literal.
        assert f'"{expected_expr}"' not in content, (
            "threshold expression was rendered as a STRING LITERAL (quoted) — "
            "that would break the generated model's semantics."
        )
        assert f"'{expected_expr}'" not in content, (
            "threshold expression was rendered as a STRING LITERAL (single-quoted)."
        )

    def test_generated_handler_method_present(self, temp_output_dir):
        """The handler method and restbus write are present in __main__.py."""
        spec = parse_yaml_string(_SEAT_ECU_GEN_YAML)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "seatecu", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        assert "async def on_seat_occupancy" in content
        assert "ChildDetectionInput.SeatOccupied" in content
        assert "restbus.update_signals" in content

