"""Full green/red acceptance matrix vs DESIGN_DECISIONS (Task 11)."""

from __future__ import annotations

from pathlib import Path

import yaml

from bmgen_eca.diagnostics import has_errors
from bmgen_eca.parser import RawEcu
from bmgen_eca.pipeline import compile_yaml
from bmgen_eca.symbols import build_symbols


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _write(tmp: Path, data: dict) -> Path:
    p = tmp / "case.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return p


def test_red_delete_target_pos(schema_v2_path, tmp_path):
    data = _load(schema_v2_path)
    data["behavior"]["state"] = [
        s for s in data["behavior"]["state"] if s["name"] != "target_pos"
    ]
    ir, diags = compile_yaml(_write(tmp_path, data))
    assert ir is None
    assert any(d.code == "E_UNRESOLVED_IDENT" for d in diags)


def test_red_delete_rx_target_position(schema_v2_path, tmp_path):
    data = _load(schema_v2_path)
    data["behavior"]["interfaces"]["can_rx"] = []
    ir, diags = compile_yaml(_write(tmp_path, data))
    assert ir is None
    assert any(d.code == "E_TRIGGER_TARGET" for d in diags)


def test_red_unknown_fn_clamp(schema_v2_path, tmp_path):
    data = _load(schema_v2_path)
    for rule in data["behavior"]["rules"]:
        for act in rule.get("actions", []):
            if isinstance(act.get("payload"), str) and act["payload"].startswith("max("):
                act["payload"] = act["payload"].replace("max(", "clamp(", 1)
    ir, diags = compile_yaml(_write(tmp_path, data))
    assert ir is None
    assert any(d.code == "E_UNKNOWN_FUNCTION" for d in diags)


def test_red_missing_ecu_name(schema_v2_path, tmp_path):
    data = _load(schema_v2_path)
    del data["ecu_mock"]
    ir, diags = compile_yaml(_write(tmp_path, data))
    assert ir is None
    assert any(d.code == "E_MISSING_ECU_NAME" for d in diags)


def test_red_bare_ident(schema_v2_path, tmp_path):
    data = _load(schema_v2_path)
    data["behavior"]["rules"][0]["condition"] = "$foo == 1"
    ir, diags = compile_yaml(_write(tmp_path, data))
    assert ir is None
    assert any(d.code == "E_BARE_IDENT" for d in diags)


def test_red_multi_bus():
    raw = RawEcu(
        ecu_name="DoorECU",
        path="multi.yaml",
        can_rx=["[BodyCAN]DoorStatus.TargetPosition"],
        can_tx=["[PowerCAN]DoorStatus.IsMoving"],
        parameters=[],
        state=[{"name": "x", "type": "float", "init": 0.0}],
        timers=[],
        rules=[],
    )
    table, diags = build_symbols(raw)
    assert table is None or has_errors(diags)
    assert any(d.code == "E_MULTI_BUS_UNSUPPORTED" for d in diags)


def test_diag_order_deterministic(schema_v2_path, tmp_path):
    data = _load(schema_v2_path)
    data["behavior"]["state"] = [
        s for s in data["behavior"]["state"] if s["name"] != "target_pos"
    ]
    p = _write(tmp_path, data)
    _, d1 = compile_yaml(p)
    _, d2 = compile_yaml(p)
    assert [d.code for d in d1] == [d.code for d in d2]
    assert [d.symbol for d in d1] == [d.symbol for d in d2]


def test_green_schema_v2(schema_v2_path):
    ir, diags = compile_yaml(schema_v2_path)
    assert not has_errors(diags)
    assert ir is not None
    assert ir.ecu_name == "DoorECU"
    assert ir.package_dir == "door_ecu"
    assert ir.namespace == "BodyCAN"
