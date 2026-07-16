from dataclasses import replace

from bmgen_eca.diagnostics import has_errors
from bmgen_eca.ir import OnRx, OnTimer
from bmgen_eca.parser import parse_file
from bmgen_eca.rules import resolve_rules
from bmgen_eca.symbols import build_symbols


def test_v2_resolve_3_rules(schema_v2_path):
    raw, _ = parse_file(schema_v2_path)
    table, d1 = build_symbols(raw)
    model, d2 = resolve_rules(raw, table)
    diags = d1 + d2
    assert not has_errors(diags)
    assert model is not None
    assert len(model.rules) == 3
    assert model.rules[0].rule_id == "receive_target"
    assert model.rules[1].rule_id == "move_door"
    assert model.rules[2].rule_id == "publish_status"
    assert [r.source_order for r in model.rules] == [0, 1, 2]
    assert isinstance(model.rules[0].trigger, OnRx)
    assert isinstance(model.rules[1].trigger, OnTimer)
    assert model.rules[1].trigger.timer_name == "tick"
    assert model.ecu_name == "DoorECU"
    # publish_status: 1 set_state + 2 tx
    assert [a.kind for a in model.rules[2].actions] == ["set_state", "tx", "tx"]


def test_bad_trigger_type(schema_v2_path):
    raw, _ = parse_file(schema_v2_path)
    table, d1 = build_symbols(raw)
    assert table is not None
    bad_rules = [
        {
            "rule_id": "bad",
            "trigger": {"type": "on_boot", "target": "x"},
            "condition": "true",
            "actions": [],
        }
    ]
    raw = replace(raw, rules=bad_rules)
    model, d2 = resolve_rules(raw, table)
    assert model is None or has_errors(d2)
    assert any(d.code == "E_BAD_TRIGGER_TYPE" for d in d2)


def test_missing_timer_trigger(schema_v2_path):
    raw, _ = parse_file(schema_v2_path)
    table, d1 = build_symbols(raw)
    assert table is not None
    bad_rules = [
        {
            "rule_id": "orphan_timer",
            "trigger": {"type": "on_timer", "target": "no_such_timer"},
            "condition": "true",
            "actions": [],
        }
    ]
    raw = replace(raw, rules=bad_rules)
    model, d2 = resolve_rules(raw, table)
    assert has_errors(d2)
    assert any(d.code == "E_TRIGGER_TARGET" for d in d2)


def test_dup_rule_id(schema_v2_path):
    raw, _ = parse_file(schema_v2_path)
    table, _ = build_symbols(raw)
    assert table is not None
    assert raw is not None
    # Duplicate first rule_id
    rules = list(raw.rules) + [dict(raw.rules[0])]
    raw = replace(raw, rules=rules)
    model, d2 = resolve_rules(raw, table)
    assert has_errors(d2)
    assert any(d.code == "E_DUP_SYMBOL" for d in d2)


def test_bad_action_type(schema_v2_path):
    raw, _ = parse_file(schema_v2_path)
    table, _ = build_symbols(raw)
    assert table is not None
    bad_rules = [
        {
            "rule_id": "bad_act",
            "trigger": {
                "type": "on_rx",
                "target": "[DoorECU-BodyCan0]DoorCmd.TargetPosition",
            },
            "condition": "true",
            "actions": [{"type": "log", "target": "x", "payload": "1"}],
        }
    ]
    raw = replace(raw, rules=bad_rules)
    model, d2 = resolve_rules(raw, table)
    assert has_errors(d2)
    assert any(d.code == "E_BAD_ACTION" for d in d2)
