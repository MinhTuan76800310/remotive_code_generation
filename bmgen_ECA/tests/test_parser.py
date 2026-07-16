from bmgen_eca.parser import parse_file


def test_parse_schema_v2(schema_v2_path):
    raw, diags = parse_file(schema_v2_path)
    assert not any(d.code.startswith("E_") for d in diags if d.severity.value == "error")
    assert raw is not None
    assert raw.ecu_name == "DoorECU"
    assert raw.can_rx == ["[BodyCAN]DoorStatus.TargetPosition"]
    assert len(raw.can_tx) == 2
    assert len(raw.parameters) == 4
    assert len(raw.state) == 3
    assert len(raw.timers) == 1
    assert len(raw.rules) == 3


def test_missing_ecu_name(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(
        "apiVersion: v1.0\n"
        "behavior:\n"
        "  interfaces:\n"
        "    can_rx: []\n"
        "    can_tx: []\n"
        "    someip_tx: []\n"
        "  parameters: []\n"
        "  state: []\n"
        "  timers: []\n"
        "  rules: []\n"
    )
    raw, diags = parse_file(p)
    assert raw is None
    assert any(d.code == "E_MISSING_ECU_NAME" for d in diags)
