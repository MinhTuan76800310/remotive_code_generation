from pathlib import Path

from bmgen_eca.diagnostics import has_errors
from bmgen_eca.semantic import compile_to_ir, snake_case


def test_snake_case():
    assert snake_case("DoorECU") == "door_ecu"
    assert snake_case("BCM") == "bcm"
    assert snake_case("MyDoorECU") == "my_door_ecu"


def test_v2_validate_green(schema_v2_path):
    ir, diags = compile_to_ir(schema_v2_path)
    assert not has_errors(diags)
    assert ir is not None
    assert ir.ecu_name == "DoorECU"
    assert ir.package_dir == "door_ecu"
    assert ir.namespace == "BodyCAN"
    assert ("BodyCAN", "DoorStatus") in ir.rx_frames
    assert "tick" in ir.timer_rules
    assert [r.rule_id for r in ir.timer_rules["tick"]] == ["move_door", "publish_status"]
    assert [r.rule_id for r in ir.rx_frames[("BodyCAN", "DoorStatus")]] == ["receive_target"]
    assert len(ir.rules) == 3


def test_red_delete_target_pos(schema_v2_path, tmp_path):
    text = schema_v2_path.read_text()
    # remove the target_pos state block (3 lines name/type/init)
    block = (
        "    - name: target_pos\n"
        "      type: float\n"
        "      init: 0.0\n"
    )
    assert block in text
    out = tmp_path / "x.yaml"
    out.write_text(text.replace(block, ""))
    ir, diags = compile_to_ir(out)
    assert ir is None
    assert any(d.code == "E_UNRESOLVED_IDENT" and "target_pos" in d.symbol for d in diags)


def test_red_delete_rx(schema_v2_path, tmp_path):
    text = schema_v2_path.read_text()
    # remove can_rx entry but leave rule that targets it
    line = '      - signal: "[BodyCAN]DoorStatus.TargetPosition"\n'
    assert line in text
    out = tmp_path / "x.yaml"
    out.write_text(text.replace(line, "      # (can_rx removed)\n", 1))
    ir, diags = compile_to_ir(out)
    assert ir is None
    assert any(d.code == "E_TRIGGER_TARGET" for d in diags)


def test_red_unknown_fn(tmp_path, schema_v2_path):
    text = schema_v2_path.read_text().replace(
        "max($para.min_pos", "clamp($para.min_pos"
    )
    out = tmp_path / "x.yaml"
    out.write_text(text)
    ir, diags = compile_to_ir(out)
    assert ir is None
    assert any(d.code == "E_UNKNOWN_FUNCTION" for d in diags)
