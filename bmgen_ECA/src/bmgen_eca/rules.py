"""Resolve RawEcu rules → RuleIR list (trigger bind + expr parse)."""

from __future__ import annotations

from typing import Any

from bmgen_eca.diagnostics import Diag, has_errors, make_diag, sort_diags
from bmgen_eca.expr import parse_expr
from bmgen_eca.ir import ActionIR, OnRx, OnTimer, ResolvedModel, RuleIR
from bmgen_eca.parser import RawEcu
from bmgen_eca.signals import parse_signal_id
from bmgen_eca.symbols import SymbolTable


def resolve_rules(
    raw: RawEcu, table: SymbolTable
) -> tuple[ResolvedModel | None, list[Diag]]:
    diags: list[Diag] = []
    path = raw.path
    seen_ids: set[str] = set()
    rules: list[RuleIR] = []

    for source_order, entry in enumerate(raw.rules):
        rule_id = entry.get("rule_id")
        if not rule_id:
            diags.append(
                make_diag(
                    "E_PARSE",
                    f"rule at index {source_order} missing rule_id",
                    path=path,
                )
            )
            rule_id = f"<missing:{source_order}>"
        else:
            rule_id = str(rule_id)
            if rule_id in seen_ids:
                diags.append(
                    make_diag(
                        "E_DUP_SYMBOL",
                        f"duplicate rule_id `{rule_id}`",
                        path=path,
                        rule_id=rule_id,
                        symbol=rule_id,
                    )
                )
            else:
                seen_ids.add(rule_id)

        trigger = _resolve_trigger(entry.get("trigger"), table, path=path, rule_id=rule_id)
        if isinstance(trigger, Diag):
            diags.append(trigger)
            trigger_ir: OnRx | OnTimer | None = None
        else:
            trigger_ir = trigger

        cond_text = entry.get("condition")
        if not isinstance(cond_text, str):
            diags.append(
                make_diag(
                    "E_BAD_EXPR",
                    f"rule `{rule_id}` condition must be a string",
                    path=path,
                    rule_id=rule_id,
                )
            )
            cond_ast: Any = None
        else:
            cond_ast, cond_diags = parse_expr(cond_text, rule_id=rule_id, path=path)
            diags.extend(cond_diags)

        actions_raw = entry.get("actions")
        if not isinstance(actions_raw, list):
            actions_raw = []
        actions: list[ActionIR] = []
        for i, act in enumerate(actions_raw):
            if not isinstance(act, dict):
                diags.append(
                    make_diag(
                        "E_BAD_ACTION",
                        f"rule `{rule_id}` action[{i}] must be a mapping",
                        path=path,
                        rule_id=rule_id,
                    )
                )
                continue
            kind = act.get("type")
            if kind not in ("tx", "set_state"):
                diags.append(
                    make_diag(
                        "E_BAD_ACTION",
                        f"rule `{rule_id}` action[{i}] type must be tx|set_state, got {kind!r}",
                        path=path,
                        rule_id=rule_id,
                        symbol=str(kind) if kind is not None else "",
                    )
                )
                continue
            target = act.get("target")
            if not target:
                diags.append(
                    make_diag(
                        "E_BAD_ACTION",
                        f"rule `{rule_id}` action[{i}] missing target",
                        path=path,
                        rule_id=rule_id,
                    )
                )
                continue
            target_name = str(target)
            payload_text = act.get("payload")
            if not isinstance(payload_text, str):
                diags.append(
                    make_diag(
                        "E_BAD_EXPR",
                        f"rule `{rule_id}` action[{i}] payload must be a string",
                        path=path,
                        rule_id=rule_id,
                        symbol=target_name,
                    )
                )
                continue
            payload_ast, payload_diags = parse_expr(
                payload_text, rule_id=rule_id, path=path
            )
            diags.extend(payload_diags)
            if payload_ast is None:
                continue
            actions.append(
                ActionIR(kind=str(kind), target_name=target_name, payload=payload_ast)
            )

        # Only keep a RuleIR when trigger + condition parsed (actions may be empty on error)
        if trigger_ir is not None and cond_ast is not None:
            rules.append(
                RuleIR(
                    rule_id=rule_id,
                    trigger=trigger_ir,
                    condition=cond_ast,
                    actions=actions,
                    source_order=source_order,
                )
            )

    diags = sort_diags(diags)
    if has_errors(diags):
        return None, diags
    return ResolvedModel(rules=rules, ecu_name=raw.ecu_name), diags


def _resolve_trigger(
    trigger: Any, table: SymbolTable, *, path: str, rule_id: str
) -> OnRx | OnTimer | Diag:
    if not isinstance(trigger, dict):
        return make_diag(
            "E_BAD_TRIGGER_TYPE",
            f"rule `{rule_id}` trigger must be a mapping",
            path=path,
            rule_id=rule_id,
        )
    ttype = trigger.get("type")
    target = trigger.get("target")
    if ttype == "on_rx":
        if not isinstance(target, str) or not target:
            return make_diag(
                "E_TRIGGER_TARGET",
                f"rule `{rule_id}` on_rx missing target",
                path=path,
                rule_id=rule_id,
            )
        sid, d = parse_signal_id(target, path=path)
        if d is not None:
            # bad form — also counts as bad trigger target for this stage
            return make_diag(
                "E_TRIGGER_TARGET",
                f"rule `{rule_id}` on_rx target invalid: {target}",
                path=path,
                rule_id=rule_id,
                symbol=target,
            )
        assert sid is not None
        if table.lookup_rx(sid) is None:
            return make_diag(
                "E_TRIGGER_TARGET",
                f"rule `{rule_id}` on_rx target not in can_rx: {sid.raw}",
                path=path,
                rule_id=rule_id,
                symbol=sid.raw,
            )
        return OnRx(signal=sid)
    if ttype == "on_timer":
        if not isinstance(target, str) or not target:
            return make_diag(
                "E_TRIGGER_TARGET",
                f"rule `{rule_id}` on_timer missing target",
                path=path,
                rule_id=rule_id,
            )
        if table.lookup_timer(target) is None:
            return make_diag(
                "E_TRIGGER_TARGET",
                f"rule `{rule_id}` on_timer target not declared: {target}",
                path=path,
                rule_id=rule_id,
                symbol=target,
            )
        return OnTimer(timer_name=target)
    return make_diag(
        "E_BAD_TRIGGER_TYPE",
        f"rule `{rule_id}` trigger.type must be on_rx|on_timer, got {ttype!r}",
        path=path,
        rule_id=rule_id,
        symbol=str(ttype) if ttype is not None else "",
    )
