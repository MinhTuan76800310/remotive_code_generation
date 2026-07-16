"""Semantic provide/consume validation → ValidatedEcaIR."""

from __future__ import annotations

import re
from pathlib import Path

from bmgen_eca.diagnostics import Diag, has_errors, make_diag, sort_diags
from bmgen_eca.expr import free_refs
from bmgen_eca.ir import OnRx, OnTimer, ResolvedModel, RuleIR, Symbol, ValidatedEcaIR
from bmgen_eca.parser import RawEcu, parse_file
from bmgen_eca.rules import resolve_rules
from bmgen_eca.symbols import SymbolTable, build_symbols

_SNAKE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_2 = re.compile(r"([a-z0-9])([A-Z])")


def snake_case(name: str) -> str:
    """DoorECU → door_ecu."""
    s1 = _SNAKE_1.sub(r"\1_\2", name)
    return _SNAKE_2.sub(r"\1_\2", s1).lower()


def validate(
    raw: RawEcu,
    table: SymbolTable,
    resolved: ResolvedModel,
) -> tuple[ValidatedEcaIR | None, list[Diag]]:
    diags: list[Diag] = []
    path = raw.path

    used_params: set[str] = set()
    used_states: set[str] = set()
    used_timers: set[str] = set()

    def _resolve_refs(expr, *, rule_id: str) -> None:
        for kind, name in free_refs(expr):
            if kind == "state":
                used_states.add(name)
                if table.lookup_state(name) is None:
                    diags.append(
                        make_diag(
                            "E_UNRESOLVED_IDENT",
                            f"unresolved $state.{name}",
                            path=path,
                            rule_id=rule_id,
                            symbol=name,
                        )
                    )
            elif kind == "para":
                used_params.add(name)
                if table.lookup_param(name) is None:
                    diags.append(
                        make_diag(
                            "E_UNRESOLVED_IDENT",
                            f"unresolved $para.{name}",
                            path=path,
                            rule_id=rule_id,
                            symbol=name,
                        )
                    )
            elif kind == "rx":
                if table.lookup_rx(name) is None:
                    diags.append(
                        make_diag(
                            "E_UNRESOLVED_IDENT",
                            f"unresolved signal ref `{name}`",
                            path=path,
                            rule_id=rule_id,
                            symbol=name,
                        )
                    )

    rx_frames: dict[tuple[str, str], list[RuleIR]] = {}
    timer_rules: dict[str, list[RuleIR]] = {}
    # preserve source_order: rules already ordered
    ordered = sorted(resolved.rules, key=lambda r: r.source_order)

    for rule in ordered:
        _resolve_refs(rule.condition, rule_id=rule.rule_id)

        if isinstance(rule.trigger, OnRx):
            key = rule.trigger.signal.frame_key
            rx_frames.setdefault(key, []).append(rule)
        elif isinstance(rule.trigger, OnTimer):
            used_timers.add(rule.trigger.timer_name)
            timer_rules.setdefault(rule.trigger.timer_name, []).append(rule)

        for act in rule.actions:
            _resolve_refs(act.payload, rule_id=rule.rule_id)
            if act.kind == "set_state":
                used_states.add(act.target_name)
                if table.lookup_state(act.target_name) is None:
                    diags.append(
                        make_diag(
                            "E_SET_STATE_UNKNOWN",
                            f"set_state target `{act.target_name}` not in state",
                            path=path,
                            rule_id=rule.rule_id,
                            symbol=act.target_name,
                        )
                    )
            elif act.kind == "tx":
                if table.lookup_tx(act.target_name) is None:
                    diags.append(
                        make_diag(
                            "E_TX_TARGET_NOT_IN_CAN_TX",
                            f"tx target `{act.target_name}` not in can_tx",
                            path=path,
                            rule_id=rule.rule_id,
                            symbol=act.target_name,
                        )
                    )

    for name in table._params:
        if name not in used_params:
            diags.append(
                make_diag(
                    "W_UNUSED_PARAM",
                    f"param `{name}` never referenced",
                    path=path,
                    symbol=name,
                )
            )
    for name in table._states:
        if name not in used_states:
            diags.append(
                make_diag(
                    "W_UNUSED_STATE",
                    f"state `{name}` never read/written",
                    path=path,
                    symbol=name,
                )
            )
    for name in table._timers:
        if name not in used_timers:
            diags.append(
                make_diag(
                    "W_UNUSED_TIMER",
                    f"timer `{name}` never on_timer target",
                    path=path,
                    symbol=name,
                )
            )

    if raw.someip_tx:
        diags.append(
            make_diag(
                "W_SOMEIP_IGNORED",
                f"someip_tx has {len(raw.someip_tx)} entries (MVP ignores SOME/IP)",
                path=path,
            )
        )

    diags = sort_diags(diags)
    if has_errors(diags):
        return None, diags

    params: list[Symbol] = list(table._params.values())
    states: list[Symbol] = list(table._states.values())
    timers: list[Symbol] = list(table._timers.values())

    ir = ValidatedEcaIR(
        ecu_name=raw.ecu_name,
        package_dir=snake_case(raw.ecu_name),
        namespace=table.bus,
        symbols=table,
        params=params,
        states=states,
        timers=timers,
        rules=ordered,
        rx_frames=rx_frames,
        timer_rules=timer_rules,
    )
    return ir, diags


def compile_to_ir(path: Path) -> tuple[ValidatedEcaIR | None, list[Diag]]:
    """Parse → symbols → resolve → validate pipeline helper for tests/CLI."""
    raw, d0 = parse_file(path)
    if raw is None:
        return None, d0
    table, d1 = build_symbols(raw)
    if table is None or has_errors(d0 + d1):
        return None, sort_diags(d0 + d1)
    resolved, d2 = resolve_rules(raw, table)
    if resolved is None or has_errors(d0 + d1 + d2):
        return None, sort_diags(d0 + d1 + d2)
    ir, d3 = validate(raw, table, resolved)
    return ir, sort_diags(d0 + d1 + d2 + d3)
