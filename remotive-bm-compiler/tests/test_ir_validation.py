"""Tests for IR validation — all invariant checks."""

import pytest

from bmgen.ir.builder import build_ir, BuilderError
from bmgen.ir.model import (
    BehavioralModelIR,
    HandlerIR,
    InputSignalIR,
    NamespaceIR,
    OutputSignalIR,
    RestbusConfigIR,
    StateIR,
)
from bmgen.ir.parser import parse_yaml_string
from bmgen.ir.validators import validate, has_errors, ValidationViolation


class TestNamespaceNameUniqueness:
    """Invariant 1: Namespace names must be unique."""

    def test_unique_namespace_names_pass(self, bcm_direct_ir):
        violations = validate(bcm_direct_ir)
        ns_violations = [v for v in violations if v.rule == "namespace_names_unique"]
        assert len(ns_violations) == 0

    def test_duplicate_namespace_names_fail(self):
        spec = """
model:
  name: BCM
  ecu_name: BCM
namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
  - name: BCM-BodyCan0
    type: can
    role: input
handlers:
  - name: on_hazard_light
    pattern: DirectSignalMapping
    input:
      namespace: BCM-BodyCan0
      frame_filter: TestFrame
      signal: TestSignal.Value
    output:
      namespace: BCM-BodyCan0
      signals:
        - Output.Signal
"""
        with pytest.raises(BuilderError) as exc_info:
            build_ir(parse_yaml_string(spec))
        assert any(v.rule == "namespace_names_unique" for v in exc_info.value.violations)


class TestHandlerNameUniqueness:
    """Invariant 2: Handler names must be unique."""

    def test_unique_handler_names_pass(self, bcm_direct_ir):
        violations = validate(bcm_direct_ir)
        handler_violations = [v for v in violations if v.rule == "handler_names_unique"]
        assert len(handler_violations) == 0

    def test_duplicate_handler_names_fail(self):
        spec = """
model:
  name: BCM
  ecu_name: BCM
namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
  - name: BCM-DriverCan0
    type: can
    role: input
handlers:
  - name: on_hazard_light
    pattern: DirectSignalMapping
    input:
      namespace: BCM-DriverCan0
      frame_filter: Frame1
      signal: Sig1.Value
    output:
      namespace: BCM-BodyCan0
      signals:
        - Out1.Signal
  - name: on_hazard_light
    pattern: DirectSignalMapping
    input:
      namespace: BCM-DriverCan0
      frame_filter: Frame2
      signal: Sig2.Value
    output:
      namespace: BCM-BodyCan0
      signals:
        - Out2.Signal
"""
        with pytest.raises(BuilderError) as exc_info:
            build_ir(parse_yaml_string(spec))
        assert any(v.rule == "handler_names_unique" for v in exc_info.value.violations)


class TestHandlerNamespaceReferences:
    """Invariants 3 & 4: Handler namespace references must exist."""

    def test_valid_namespace_refs_pass(self, bcm_direct_ir):
        violations = validate(bcm_direct_ir)
        ns_violations = [v for v in violations if v.rule in ("handler_input_namespace_exists", "handler_output_namespace_exists")]
        assert len(ns_violations) == 0

    def test_nonexistent_input_namespace_fail(self):
        spec = """
model:
  name: BCM
  ecu_name: BCM
namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
handlers:
  - name: on_test
    pattern: DirectSignalMapping
    input:
      namespace: NONEXISTENT-NAMESPACE
      frame_filter: Test
      signal: Test.Value
    output:
      namespace: BCM-BodyCan0
      signals:
        - Out.Signal
"""
        with pytest.raises(BuilderError) as exc_info:
            build_ir(parse_yaml_string(spec))
        assert any(v.rule == "handler_input_namespace_exists" for v in exc_info.value.violations)

    def test_nonexistent_output_namespace_fail(self):
        spec = """
model:
  name: BCM
  ecu_name: BCM
namespaces:
  - name: BCM-DriverCan0
    type: can
    role: input
handlers:
  - name: on_test
    pattern: DirectSignalMapping
    input:
      namespace: BCM-DriverCan0
      frame_filter: Test
      signal: Test.Value
    output:
      namespace: NONEXISTENT-NAMESPACE
      signals:
        - Out.Signal
"""
        with pytest.raises(BuilderError) as exc_info:
            build_ir(parse_yaml_string(spec))
        assert any(v.rule == "handler_output_namespace_exists" for v in exc_info.value.violations)


class TestOutputNamespaceRestbus:
    """Invariant 5: Output namespace must have restbus config."""

    def test_output_with_restbus_pass(self, bcm_direct_ir):
        violations = validate(bcm_direct_ir)
        restbus_violations = [v for v in violations if v.rule == "output_namespace_has_restbus"]
        assert len(restbus_violations) == 0

    def test_output_without_restbus_fail(self):
        spec = """
model:
  name: BCM
  ecu_name: BCM
namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
  - name: BCM-DriverCan0
    type: can
    role: input
handlers:
  - name: on_test
    pattern: DirectSignalMapping
    input:
      namespace: BCM-DriverCan0
      frame_filter: Test
      signal: Test.Value
    output:
      namespace: BCM-BodyCan0
      signals:
        - Out.Signal
"""
        with pytest.raises(BuilderError) as exc_info:
            build_ir(parse_yaml_string(spec))
        assert any(v.rule == "output_namespace_has_restbus" for v in exc_info.value.violations)


class TestUnknownPattern:
    """Invariant 9: Unknown pattern must fail early unless novel_logic=True."""

    def test_known_pattern_pass(self, bcm_direct_ir):
        violations = validate(bcm_direct_ir)
        pattern_violations = [v for v in violations if v.rule == "unknown_pattern_fails_early"]
        assert len(pattern_violations) == 0

    def test_unknown_pattern_fail(self):
        spec = """
model:
  name: BCM
  ecu_name: BCM
namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
  - name: BCM-DriverCan0
    type: can
    role: input
handlers:
  - name: on_custom
    pattern: CustomBehavior
    input:
      namespace: BCM-DriverCan0
      frame_filter: Test
      signal: Test.Value
    output:
      namespace: BCM-BodyCan0
      signals:
        - Out.Signal
"""
        with pytest.raises(BuilderError) as exc_info:
            build_ir(parse_yaml_string(spec))
        assert any(v.rule == "unknown_pattern_fails_early" for v in exc_info.value.violations)

    def test_unknown_pattern_with_novel_logic_pass(self):
        spec = """
model:
  name: BCM
  ecu_name: BCM
namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
  - name: BCM-DriverCan0
    type: can
    role: input
handlers:
  - name: on_custom
    pattern: CustomBehavior
    novel_logic: true
    input:
      namespace: BCM-DriverCan0
      frame_filter: Test
      signal: Test.Value
    output:
      namespace: BCM-BodyCan0
      signals:
        - Out.Signal
"""
        ir = build_ir(parse_yaml_string(spec))
        assert ir.handlers[0].novel_logic is True
        assert "on_custom" in ir.novel_logic_handlers


class TestDerivedPythonVarNames:
    """Test that namespace and signal Python variable names are derived correctly."""

    def test_namespace_var_name_derivation(self, bcm_direct_ir):
        ns_names = {ns.python_var_name for ns in bcm_direct_ir.namespaces}
        assert "body_can_0" in ns_names
        assert "driver_can_0" in ns_names

    def test_signal_var_name_derivation(self, bcm_direct_ir):
        handler = bcm_direct_ir.handlers[0]
        assert handler.input_signals[0].python_var_name == "hazard_light_button_signal"


class TestToggleButtonIRConstruction:
    """Test ToggleButtonState IR construction and validation."""

    def test_toggle_ir_has_state(self, bcm_toggle_ir):
        handler = bcm_toggle_ir.handlers[0]
        assert handler.state is not None
        assert handler.state.name == "hazard_enabled"
        assert handler.state.type == "bool"
        assert handler.state.initial is False
        assert handler.state.reset_value is False

    def test_toggle_ir_has_reset_handler(self, bcm_toggle_ir):
        assert bcm_toggle_ir.reset_handler is not None
        assert len(bcm_toggle_ir.reset_handler.states_to_reset) > 0
