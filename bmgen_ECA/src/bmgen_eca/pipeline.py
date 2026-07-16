"""Pipeline driver: compile_yaml (+ generate stub until codegen Task 9)."""

from __future__ import annotations

from pathlib import Path

from bmgen_eca.diagnostics import Diag, has_errors, sort_diags
from bmgen_eca.ir import ValidatedEcaIR
from bmgen_eca.parser import parse_file
from bmgen_eca.rules import resolve_rules
from bmgen_eca.semantic import validate
from bmgen_eca.symbols import build_symbols


def compile_yaml(path: Path) -> tuple[ValidatedEcaIR | None, list[Diag]]:
    """Parse → symbols → resolve → validate. No codegen."""
    raw, d0 = parse_file(path)
    if raw is None:
        return None, sort_diags(d0)
    table, d1 = build_symbols(raw)
    if table is None or has_errors(d0 + d1):
        return None, sort_diags(d0 + d1)
    resolved, d2 = resolve_rules(raw, table)
    if resolved is None or has_errors(d0 + d1 + d2):
        return None, sort_diags(d0 + d1 + d2)
    ir, d3 = validate(raw, table, resolved)
    return ir, sort_diags(d0 + d1 + d2 + d3)


def generate(path: Path, out_dir: Path) -> tuple[Path | None, list[Diag]]:
    """Compile then write package. Codegen wired in Task 9; until then returns IR-only failure if errors."""
    ir, diags = compile_yaml(path)
    if ir is None or has_errors(diags):
        return None, diags
    # Task 9 will call write_artifacts(ir, out_dir)
    try:
        from bmgen_eca.codegen import write_artifacts
    except ImportError:
        return None, diags  # codegen not ready
    pkg = write_artifacts(ir, out_dir)
    return pkg, diags
