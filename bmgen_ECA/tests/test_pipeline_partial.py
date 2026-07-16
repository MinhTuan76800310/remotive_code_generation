from bmgen_eca.diagnostics import has_errors
from bmgen_eca.pipeline import compile_yaml


def test_compile_yaml_green(schema_v2_path):
    ir, diags = compile_yaml(schema_v2_path)
    assert not has_errors(diags)
    assert ir is not None
    assert ir.ecu_name == "DoorECU"
    assert ir.package_dir == "door_ecu"
    assert ir.namespace == "BodyCAN"
    assert ("BodyCAN", "DoorStatus") in ir.rx_frames
    assert "tick" in ir.timer_rules
    assert [r.rule_id for r in ir.timer_rules["tick"]] == [
        "move_door",
        "publish_status",
    ]


def test_compile_yaml_missing_name(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "apiVersion: v1.0\n"
        "behavior:\n"
        "  interfaces: {can_rx: [], can_tx: [], someip_tx: []}\n"
        "  parameters: []\n"
        "  state: []\n"
        "  timers: []\n"
        "  rules: []\n"
    )
    ir, diags = compile_yaml(p)
    assert ir is None
    assert any(d.code == "E_MISSING_ECU_NAME" for d in diags)
