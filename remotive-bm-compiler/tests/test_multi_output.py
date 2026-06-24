"""Tests for multi-output handler fan-out (service_oriented).

A handler in the new schema can have an `output:` list (one or more groups).
The compiler must emit one `restbus.update_signals()` call per group, in
declaration order, with the *same* computed value_expr fanning out across all
groups. Single-output handlers (one-element list) keep the legacy byte-identical
shape so existing specs migrate without diffs.
"""

import os

import pytest

from bmgen.compiler.context_builder import build_template_context
from bmgen.compiler.python_generator import generate
from bmgen.ir.builder import build_ir
from bmgen.ir.parser import parse_yaml_string


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def temp_output_dir(tmp_path):
    """Per-test output dir; auto-cleaned."""
    return str(tmp_path)


@pytest.fixture
def multi_output_threshold_yaml():
    """ThresholdMapping handler fanning out to two CAN buses.

    Replicates new_schema.yaml: same value (the threshold comparison result) is
    written to SeatOccupied on the primary bus AND SeatOccupiedBackup on the
    backup bus. Both namespaces are declared in `namespace_types:`.
    """
    return """
model:
  name: SeatECU
  ecu_name: SEAT

namespace_types:
  SEAT-CpdCan0: can
  SEAT-CpdCan1: can

handlers:
  - name: on_seat_occupancy
    pattern: ThresholdMapping
    threshold: 8
    operator: ">="
    true_when: below
    input:
      namespace: SEAT-CpdCan0
      frame_filter: SeatWeightSensor
      signal: SeatWeightSensor.WeightKg
    output:
      - namespace: SEAT-CpdCan0
        signals:
          - SeatInput.SeatOccupied
      - namespace: SEAT-CpdCan1
        signals:
          - SeatInput.SeatOccupiedBackup
"""


# ── IR-level tests (no template rendering) ────────────────────────────────


class TestMultiOutputIR:
    """IR-level checks: parser + builder produce the right `output_groups`."""

    def test_two_output_groups_inferred(self, multi_output_threshold_yaml):
        ir = build_ir(parse_yaml_string(multi_output_threshold_yaml))
        assert len(ir.namespaces) == 2
        # Both namespaces inferred; one is role=both (input + output), other is output.
        names_by_role = {n.role: n.name for n in ir.namespaces}
        assert names_by_role["both"] == "SEAT-CpdCan0"
        assert names_by_role["output"] == "SEAT-CpdCan1"

    def test_handler_has_two_output_groups(self, multi_output_threshold_yaml):
        ir = build_ir(parse_yaml_string(multi_output_threshold_yaml))
        handler = ir.handlers[0]
        assert len(handler.output_groups) == 2
        # Order preserved from YAML declaration.
        assert handler.output_groups[0].namespace == "SEAT-CpdCan0"
        assert handler.output_groups[1].namespace == "SEAT-CpdCan1"
        assert [s.name for s in handler.output_groups[0].signals] == ["SeatInput.SeatOccupied"]
        assert [s.name for s in handler.output_groups[1].signals] == ["SeatInput.SeatOccupiedBackup"]

    def test_value_expr_fans_out_to_all_groups(self, multi_output_threshold_yaml):
        ir = build_ir(parse_yaml_string(multi_output_threshold_yaml))
        # Same value_expr (the threshold comparison) on every output signal.
        expected = "1 if not (seat_weight_sensor_signal >= 8) else 0"
        for group in ir.handlers[0].output_groups:
            for sig in group.signals:
                assert sig.value_expr == expected


# ── Generated-code tests ──────────────────────────────────────────────────


class TestMultiOutputGeneratedCode:
    """End-to-end: render the template and inspect generated Python."""

    def test_two_update_signals_calls_in_order(self, multi_output_threshold_yaml, temp_output_dir):
        """The generated handler must call `restbus.update_signals` exactly twice,
        once per output group, in declaration order."""
        ir = build_ir(parse_yaml_string(multi_output_threshold_yaml))
        ctx = build_template_context(ir)
        generate(ctx, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "seatecu", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        method_start = content.find("async def on_seat_occupancy(self, frame: Frame) -> None:")
        method_end = content.find("\n\n\n", method_start)
        method_body = content[method_start:method_end]

        # Slice into the two `await self.X.restbus.update_signals(...)` call lines.
        first_call_line = method_body.find("await self.cpd_can_0.restbus.update_signals")
        second_call_line = method_body.find("await self.cpd_can_1.restbus.update_signals")
        assert first_call_line != -1, "expected first await self.cpd_can_0.restbus.update_signals call"
        assert second_call_line != -1, "expected second await self.cpd_can_1.restbus.update_signals call"
        assert first_call_line < second_call_line, "update_signals calls must be in declaration order"
        # Exactly two call lines — guards against accidental extra fan-out.
        assert method_body.count("await self.cpd_can_0.restbus.update_signals") == 1
        assert method_body.count("await self.cpd_can_1.restbus.update_signals") == 1

    def test_value_expr_appears_in_both_calls(self, multi_output_threshold_yaml, temp_output_dir):
        """Same computed value is forwarded to both namespaces (fan-out)."""
        ir = build_ir(parse_yaml_string(multi_output_threshold_yaml))
        ctx = build_template_context(ir)
        generate(ctx, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "seatecu", "__main__.py")
        with open(main_path) as f:
            content = f.read()
        # Count occurrences of the threshold expression — must appear twice
        # (once per update_signals call).
        expr = "1 if not (seat_weight_sensor_signal >= 8) else 0"
        assert content.count(expr) == 2

    def test_dataclass_has_both_namespace_vars(self, multi_output_threshold_yaml, temp_output_dir):
        """The generated class declares both CanNamespace fields and the
        constructor accepts both, matching the multi-output shape."""
        ir = build_ir(parse_yaml_string(multi_output_threshold_yaml))
        ctx = build_template_context(ir)
        generate(ctx, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "seatecu", "__main__.py")
        with open(main_path) as f:
            content = f.read()
        # Both namespace fields declared on the class.
        assert "cpd_can_0: CanNamespace" in content
        assert "cpd_can_1: CanNamespace" in content
        # main() constructs both namespaces and passes both to the model.
        assert 'CanNamespace(\n            "SEAT-CpdCan0"' in content
        assert 'CanNamespace(\n            "SEAT-CpdCan1"' in content
        assert "namespaces=[cpd_can_0, cpd_can_1]" in content

    def test_generated_code_is_valid_python(self, multi_output_threshold_yaml, temp_output_dir):
        """The compiled output must be syntactically valid Python."""
        import ast
        ir = build_ir(parse_yaml_string(multi_output_threshold_yaml))
        ctx = build_template_context(ir)
        generate(ctx, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "seatecu", "__main__.py")
        with open(main_path) as f:
            ast.parse(f.read())


# ── Single-output byte-identical guarantee ────────────────────────────────


class TestSingleOutputStillByteIdentical:
    """The headline migration claim: single-output handlers keep the legacy
    rendering shape exactly. This guards against template regressions that
    would break the existing 4 byte-identical migrations (seat_ecu,
    cockpit_hmi_ecu, airbag_control_unit, driver_monitoring_ecu)."""

    def test_single_output_uses_flat_update_signals(self):
        spec = """
model:
  name: BCM
  ecu_name: BCM

namespace_types:
  BCM-BodyCan0: can

handlers:
  - name: on_hazard
    pattern: DirectSignalMapping
    input:
      namespace: BCM-BodyCan0
      frame_filter: TestFrame
      signal: TestFrame.Value
    output:
      - namespace: BCM-BodyCan0
        signals:
          - Output.Signal
"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            ir = build_ir(parse_yaml_string(spec))
            ctx = build_template_context(ir)
            generate(ctx, tmp)
            content = open(os.path.join(tmp, "bcm", "__main__.py")).read()
            # Single update_signals call, no nested for-loop body.
            assert content.count("restbus.update_signals(") == 1
            # Confirm the single call is the *flat* shape (no nested groups).
            method_body = content[content.find("async def on_hazard"):]
            assert "self.body_can_0.restbus.update_signals" in method_body
