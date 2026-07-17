"""Jinja codegen: ValidatedEcaIR → Remotive BM package files."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from bmgen_eca.expr import free_refs, lower_expr
from bmgen_eca.ir import ActionIR, RuleIR, Symbol, ValidatedEcaIR
from bmgen_eca.semantic import snake_case


def _py_type(type_name: str | None) -> str:
    if type_name in ("bool", "int", "float", "str"):
        return type_name  # type: ignore[return-value]
    return "float"


def _py_lit(value: Any) -> str:
    if value is True:
        return "True"
    if value is False:
        return "False"
    if isinstance(value, str):
        return repr(value)
    return repr(value)


def _signal_local(raw: str, signal_leaf: str) -> str:
    return snake_case(signal_leaf)


def _remotive_signal_key(raw: str) -> str:
    """`[Bus]Frame.Signal` → `Frame.Signal` for Remotive frame.signals / restbus keys."""
    if "]" in raw:
        return raw.split("]", 1)[1]
    return raw


def _collect_signal_reads(rules: list[RuleIR]) -> list[dict[str, str]]:
    """RX signal leaves used by rules → local bindings from frame.signals."""
    seen: dict[str, dict[str, str]] = {}
    for rule in rules:
        exprs = [rule.condition] + [a.payload for a in rule.actions]
        for expr in exprs:
            for kind, name in free_refs(expr):
                if kind != "rx" or name in seen:
                    continue
                # name is SignalId.raw; Remotive key drops [Bus]
                leaf = name.rsplit(".", 1)[-1]
                local = _signal_local(name, leaf)
                seen[name] = {
                    "local": local,
                    "key": _remotive_signal_key(name),
                    "raw": name,
                }
    return list(seen.values())


def _signal_locals_map(reads: list[dict[str, str]]) -> dict[str, str]:
    # lower_expr looks up SignalRef by SignalId.raw
    return {r["raw"]: r["local"] for r in reads}


def _cast_state_rhs(name: str, rhs: str, state_types: dict[str, str]) -> str:
    """Cast numpy scalars from min/max/abs to native Python for Remotive restbus."""
    typ = state_types.get(name)
    if typ == "float":
        return f"float({rhs})"
    if typ == "bool":
        return f"bool({rhs})"
    if typ == "int":
        return f"int({rhs})"
    return rhs


def _lower_actions(
    actions: list[ActionIR],
    *,
    ns_var: str,
    signal_locals: dict[str, str],
    state_types: dict[str, str],
) -> list[str]:
    """Lower actions; batch consecutive tx into one update_signals call."""
    lines: list[str] = []
    i = 0
    while i < len(actions):
        act = actions[i]
        if act.kind == "set_state":
            rhs = lower_expr(act.payload, signal_locals=signal_locals)
            lines.append(
                f"self.{act.target_name} = {_cast_state_rhs(act.target_name, rhs, state_types)}"
            )
            i += 1
            continue
        if act.kind == "tx":
            pairs: list[str] = []
            while i < len(actions) and actions[i].kind == "tx":
                a = actions[i]
                val = lower_expr(a.payload, signal_locals=signal_locals)
                key = _remotive_signal_key(a.target_name)
                # _net(): restbus rejects np.float64 / np.bool_ from abs/min/compare.
                pairs.append(f'("{key}", _net({val}))')
                i += 1
            args = ",\n                ".join(pairs)
            if len(pairs) == 1:
                lines.append(
                    f"await self.{ns_var}.restbus.update_signals({pairs[0]})"
                )
            else:
                lines.append(
                    f"await self.{ns_var}.restbus.update_signals(\n"
                    f"                {args},\n"
                    f"            )"
                )
            continue
        i += 1
    return lines


def _lower_rule(
    rule: RuleIR,
    *,
    ns_var: str,
    signal_locals: dict[str, str],
    state_types: dict[str, str],
) -> dict[str, Any]:
    cond = lower_expr(rule.condition, signal_locals=signal_locals)
    # Drop trivial True wrapping parens from lowerer for lit true → "True"
    always = cond == "True"
    return {
        "rule_id": rule.rule_id,
        "condition_py": cond,
        "always": always,
        "actions_py": _lower_actions(
            rule.actions,
            ns_var=ns_var,
            signal_locals=signal_locals,
            state_types=state_types,
        ),
    }


def build_context(ir: ValidatedEcaIR) -> dict[str, Any]:
    ns_var = snake_case(ir.namespace)
    model_var = snake_case(ir.ecu_name)

    params = [
        {
            "name": p.name,
            "type": _py_type(p.type_name),
            "value": _py_lit(p.meta.get("value", 0.0)),
        }
        for p in ir.params
    ]
    states = [
        {
            "name": s.name,
            "type": _py_type(s.type_name),
            "init": _py_lit(s.meta.get("init", 0.0)),
        }
        for s in ir.states
    ]
    state_types = {s["name"]: s["type"] for s in states}

    handlers: list[dict[str, Any]] = []
    # stable order: sorted by (bus, frame)
    for (bus, frame), rules in sorted(ir.rx_frames.items(), key=lambda kv: kv[0]):
        reads = _collect_signal_reads(rules)
        locs = _signal_locals_map(reads)
        handlers.append(
            {
                "method": f"on_{frame}",
                "frame": frame,
                "bus": bus,
                "signal_reads": reads,
                "rules": [
                    _lower_rule(
                        r,
                        ns_var=ns_var,
                        signal_locals=locs,
                        state_types=state_types,
                    )
                    for r in rules
                ],
            }
        )

    tickers: list[dict[str, Any]] = []
    for t in ir.timers:
        if not t.meta.get("auto_start"):
            continue
        rules = ir.timer_rules.get(t.name, [])
        tickers.append(
            {
                "name": t.name,
                "interval": t.meta.get("interval", 0.1),
                "method": f"_loop_{t.name}",
                "task_var": f"_ticker_{t.name}",
                "rules": [
                    _lower_rule(
                        r,
                        ns_var=ns_var,
                        signal_locals={},
                        state_types=state_types,
                    )
                    for r in rules
                ],
            }
        )

    return {
        "ecu_name": ir.ecu_name,
        "model_var": model_var,
        "namespace": ir.namespace,
        "ns_var": ns_var,
        "params": params,
        "states": states,
        "handlers": handlers,
        "tickers": tickers,
    }


def _env() -> Environment:
    return Environment(
        loader=PackageLoader("bmgen_eca.codegen", "templates"),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render(ir: ValidatedEcaIR) -> dict[str, str]:
    """Render package files: relative path → content."""
    ctx = build_context(ir)
    env = _env()
    return {
        "__init__.py": env.get_template("init.py.j2").render(**ctx),
        "__main__.py": env.get_template("main.py.j2").render(**ctx),
    }


def write_artifacts(ir: ValidatedEcaIR, out_root: Path) -> Path:
    """Write `{out_root}/bmgen_generated/{package_dir}/` and return that Path."""
    pkg = Path(out_root) / "bmgen_generated" / ir.package_dir
    pkg.mkdir(parents=True, exist_ok=True)
    for name, content in render(ir).items():
        (pkg / name).write_text(content, encoding="utf-8")
    return pkg
