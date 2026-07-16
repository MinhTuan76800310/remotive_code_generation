from dataclasses import replace

from bmgen_eca.diagnostics import has_errors
from bmgen_eca.parser import RawEcu, parse_file
from bmgen_eca.symbols import build_symbols


def test_v2_symbols(schema_v2_path):
    raw, _ = parse_file(schema_v2_path)
    table, diags = build_symbols(raw)
    assert not has_errors(diags)
    assert table is not None
    assert table.lookup_rx("[BodyCAN]DoorStatus.TargetPosition") is not None
    assert table.lookup_tx("[BodyCAN]DoorStatus.IsMoving") is not None
    assert table.lookup_tx("[BodyCAN]DoorStatus.CurrentPosition") is not None
    assert table.lookup_param("move_step") is not None
    assert table.lookup_param("min_pos") is not None
    assert table.lookup_param("max_pos") is not None
    assert table.lookup_param("pos_tolerance") is not None
    assert table.lookup_state("target_pos") is not None
    assert table.lookup_state("current_pos") is not None
    assert table.lookup_state("door_moving") is not None
    assert table.lookup_timer("tick") is not None
    assert table.bus == "BodyCAN"


def test_dup_param(schema_v2_path):
    raw, _ = parse_file(schema_v2_path)
    assert raw is not None
    # Duplicate move_step under parameters
    raw = replace(
        raw,
        parameters=list(raw.parameters)
        + [{"name": "move_step", "type": "float", "value": 1.0}],
    )
    table, diags = build_symbols(raw)
    assert table is None or has_errors(diags)
    assert any(d.code == "E_DUP_SYMBOL" for d in diags)


def test_multi_bus_error():
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


def test_missing_init(schema_v2_path):
    raw, _ = parse_file(schema_v2_path)
    assert raw is not None
    bad_state = [{"name": "broken", "type": "float"}]  # no init
    raw = replace(raw, state=list(raw.state) + bad_state)
    table, diags = build_symbols(raw)
    assert has_errors(diags)
    assert any(d.code == "E_MISSING_INIT" for d in diags)


def test_bad_timer_interval(schema_v2_path):
    raw, _ = parse_file(schema_v2_path)
    assert raw is not None
    raw = replace(
        raw,
        timers=[{"name": "bad", "interval": 0, "auto_start": True}],
    )
    table, diags = build_symbols(raw)
    assert has_errors(diags)
    assert any(d.code == "E_BAD_TIMER_INTERVAL" for d in diags)
