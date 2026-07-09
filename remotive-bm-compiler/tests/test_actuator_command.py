"""Tests for the ActuatorCommand recipe — edge-triggered status publish.

Pins down:
1. REGISTRATION — recipe is in the default registry.
2. IR BUILD — auto-synthesises StateIR from pattern_params (no explicit state:).
3. VALIDATION — 1 input / ≥1 output / value_type closed set.
4. GENERATION — rendered handler does edge compare + publish 1; cast matches value_type.
5. END-TO-END — vehicle_functions OCS SWC_seat_actuator_command.yaml compiles.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from bmgen.compiler.context_builder import build_template_context
from bmgen.compiler.python_generator import generate
from bmgen.ir.builder import build_ir, BuilderError
from bmgen.ir.model import HandlerIR, InputSignalIR, OutputGroupIR, OutputSignalIR, StateIR
from bmgen.ir.parser import parse_yaml_string
from bmgen.recipes.actuator_command import ActuatorCommandRecipe
from bmgen.recipes.registry import create_default_registry


_BASE_ACTUATOR_YAML = """
model:
  name: SeatECU
  ecu_name: SEAT

namespaces:
  - name: SE-BodyCAN
    type: can
    role: both
    restbus:
      sender_filter: SEAT

handlers:
  - name: on_seat_cmd
    pattern:
      - name: ActuatorCommand
        value_type: int
        initial_state: -1
    input:
      namespace: SE-BodyCAN
      signal: PW_SeatCmd.SeatPosTarget
    output:
      - namespace: SE-BodyCAN
        signals: [PW_SeatStatus.SeatDone]
"""


def _make_handler_ir(
    *,
    value_type: str = "int",
    initial: int | float | bool | str = -1,
    n_inputs: int = 1,
    n_outputs: int = 1,
    with_state: bool = True,
    with_periodic: bool = False,
) -> HandlerIR:
    inputs = [
        InputSignalIR(name="PW_SeatCmd.SeatPosTarget")
    ] * n_inputs if n_inputs else []
    # rebuild unique names if multiple
    if n_inputs > 1:
        inputs = [
            InputSignalIR(name=f"PW_SeatCmd.Sig{i}") for i in range(n_inputs)
        ]
    outputs = [
        OutputSignalIR(name="PW_SeatStatus.SeatDone", value_expr="1")
    ]
    if n_outputs > 1:
        outputs = [
            OutputSignalIR(name=f"PW_SeatStatus.Done{i}", value_expr="1")
            for i in range(n_outputs)
        ]
    state = None
    if with_state:
        state = StateIR(
            name="last_on_seat_cmd",
            type=value_type,
            initial=initial,
            reset_value=initial,
            owner="on_seat_cmd",
        )
    from bmgen.ir.model import PeriodicTaskIR
    periodic = None
    if with_periodic:
        periodic = PeriodicTaskIR(
            interval_sec=1.0,
            blink_output_namespace="SE-BodyCAN",
            blink_output_signals=["X"],
            cleanup=True,
        )
    return HandlerIR(
        name="on_seat_cmd",
        pattern="ActuatorCommand",
        input_namespace="SE-BodyCAN",
        input_frame_filter="PW_SeatCmd",
        input_signals=inputs,
        output_groups=[OutputGroupIR(namespace="SE-BodyCAN", signals=outputs)],
        state=state,
        periodic_task=periodic,
        pattern_params={"value_type": value_type, "initial_state": initial},
    )


class TestActuatorCommandRegistration:
    def test_recipe_registered(self):
        reg = create_default_registry()
        r = reg.get("ActuatorCommand")
        assert r is not None
        assert r.name == "ActuatorCommand"
        assert "ActuatorCommand" in reg.known_patterns()

    def test_required_fields_advertise_options(self):
        r = ActuatorCommandRecipe()
        fields = r.required_fields()
        assert fields["requires_state"] is True
        assert fields["state_auto_synthesised"] is True
        assert fields["publish_on_edge"] == 1
        assert "int" in fields["optional_value_type"]


class TestActuatorCommandValidation:
    def test_accepts_valid(self):
        r = ActuatorCommandRecipe()
        assert r.validate(_make_handler_ir()) == []

    def test_rejects_zero_inputs(self):
        r = ActuatorCommandRecipe()
        errs = r.validate(_make_handler_ir(n_inputs=0))
        assert any("exactly 1 input" in e for e in errs)

    def test_rejects_two_inputs(self):
        r = ActuatorCommandRecipe()
        errs = r.validate(_make_handler_ir(n_inputs=2))
        assert any("exactly 1 input" in e for e in errs)

    def test_rejects_zero_outputs(self):
        r = ActuatorCommandRecipe()
        h = _make_handler_ir(n_outputs=0)
        # force empty groups
        h.output_groups = [OutputGroupIR(namespace="SE-BodyCAN", signals=[])]
        errs = r.validate(h)
        assert any("at least 1 output" in e for e in errs)

    def test_rejects_missing_state(self):
        r = ActuatorCommandRecipe()
        errs = r.validate(_make_handler_ir(with_state=False))
        assert any("state" in e.lower() for e in errs)

    def test_rejects_periodic(self):
        r = ActuatorCommandRecipe()
        errs = r.validate(_make_handler_ir(with_periodic=True))
        assert any("periodic" in e.lower() for e in errs)

    def test_rejects_bad_value_type(self):
        r = ActuatorCommandRecipe()
        h = _make_handler_ir()
        h.pattern_params["value_type"] = "decimal"
        errs = r.validate(h)
        assert any("value_type" in e for e in errs)

    def test_output_value_expr_is_one(self):
        r = ActuatorCommandRecipe()
        assert r.output_value_expr(_make_handler_ir()) == "1"


class TestActuatorCommandIRBuild:
    def test_auto_synthesises_state(self):
        ir = build_ir(parse_yaml_string(_BASE_ACTUATOR_YAML))
        h = next(x for x in ir.handlers if x.name == "on_seat_cmd")
        assert h.pattern == "ActuatorCommand"
        assert h.state is not None
        assert h.state.name == "last_on_seat_cmd"
        assert h.state.type == "int"
        assert h.state.initial == -1
        assert h.state.reset_value == -1
        assert h.pattern_params.get("value_type") == "int"
        assert h.input_frame_filter == "PW_SeatCmd"

    def test_value_exprs_are_one(self):
        ir = build_ir(parse_yaml_string(_BASE_ACTUATOR_YAML))
        h = next(x for x in ir.handlers if x.name == "on_seat_cmd")
        for g in h.output_groups:
            for s in g.signals:
                assert s.value_expr == "1"

    def test_unknown_value_type_falls_back_to_int_state(self):
        yaml = _BASE_ACTUATOR_YAML.replace("value_type: int", "value_type: decimal")
        # builder falls back to int for unknown types; recipe.validate will reject
        ir = build_ir(parse_yaml_string(yaml))
        h = next(x for x in ir.handlers if x.name == "on_seat_cmd")
        assert h.state is not None
        assert h.state.type == "int"


class TestActuatorCommandGeneration:
    def test_generated_main_py_is_valid_python(self, temp_output_dir):
        ir = build_ir(parse_yaml_string(_BASE_ACTUATOR_YAML))
        ctx = build_template_context(ir)
        generate(ctx, temp_output_dir)
        main_py = Path(temp_output_dir) / "seatecu" / "__main__.py"
        assert main_py.exists()
        source = main_py.read_text()
        ast.parse(source)

    def test_handler_edge_compare_and_publish_one(self, temp_output_dir):
        ir = build_ir(parse_yaml_string(_BASE_ACTUATOR_YAML))
        ctx = build_template_context(ir)
        generate(ctx, temp_output_dir)
        source = (Path(temp_output_dir) / "seatecu" / "__main__.py").read_text()

        assert "async def on_seat_cmd(self, frame: Frame) -> None:" in source
        assert 'int(frame.signals["PW_SeatCmd.SeatPosTarget"])' in source
        assert "self._last_on_seat_cmd" in source
        assert "if " in source and "!= self._last_on_seat_cmd" in source
        assert '("PW_SeatStatus.SeatDone", 1)' in source
        # class field initialised to -1
        assert "_last_on_seat_cmd: int = -1" in source

    def test_float_value_type_cast(self, temp_output_dir):
        yaml = _BASE_ACTUATOR_YAML.replace("value_type: int", "value_type: float").replace(
            "initial_state: -1", "initial_state: -1.0"
        )
        ir = build_ir(parse_yaml_string(yaml))
        ctx = build_template_context(ir)
        generate(ctx, temp_output_dir)
        source = (Path(temp_output_dir) / "seatecu" / "__main__.py").read_text()
        assert 'float(frame.signals["PW_SeatCmd.SeatPosTarget"])' in source
        assert "_last_on_seat_cmd: float = -1.0" in source


class TestActuatorCommandIncSchemaE2E:
    """Compile the real OCS SWC against seatECU parent."""

    def test_seat_ecu_with_actuator_swc(self, temp_output_dir):
        root = Path(__file__).resolve().parents[2]
        # repo root = code_generation/; tests live under remotive-bm-compiler/tests/
        # parents[0]=tests, [1]=remotive-bm-compiler, [2]=code_generation
        ecu_yaml = (
            root
            / "vehicle_functions"
            / "occupant_classification"
            / "inc_schema"
            / "seatECU.yaml"
        )
        if not ecu_yaml.exists():
            pytest.skip(f"missing {ecu_yaml}")

        from bmgen.ir.parser import parse_yaml_file

        spec = parse_yaml_file(str(ecu_yaml))
        ir = build_ir(spec, base_dir=ecu_yaml.parent)
        names = {h.name for h in ir.handlers}
        assert "on_seat_cmd" in names
        h = next(x for x in ir.handlers if x.name == "on_seat_cmd")
        assert h.pattern == "ActuatorCommand"
        assert h.state is not None
        assert h.state.initial == -1

        ctx = build_template_context(ir)
        files = generate(ctx, temp_output_dir)
        assert any(f.endswith("__main__.py") for f in files)
        main = Path(temp_output_dir) / ir.name.lower() / "__main__.py"
        source = main.read_text()
        ast.parse(source)
        assert "async def on_seat_cmd" in source
        assert '("PW_SeatStatus.SeatDone", 1)' in source
