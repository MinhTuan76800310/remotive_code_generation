"""Post-codegen package verify gate (MVP: ast.parse only)."""
from __future__ import annotations

import ast
from pathlib import Path

from bmgen_eca.diagnostics import Diag, Severity, sort_diags


def verify_package(dir: Path) -> list[Diag]:
    """ast.parse every ``.py`` under *dir*. Live Remotive import is out of MVP."""
    root = Path(dir)
    diags: list[Diag] = []
    if not root.is_dir():
        diags.append(
            Diag(
                severity=Severity.ERROR,
                code="E_PARSE",
                message=f"package directory not found: {root}",
                path=str(root),
            )
        )
        return diags

    for py in sorted(root.rglob("*.py")):
        try:
            src = py.read_text(encoding="utf-8")
            ast.parse(src, filename=str(py))
        except SyntaxError as e:
            diags.append(
                Diag(
                    severity=Severity.ERROR,
                    code="E_PARSE",
                    message=f"syntax error in {py}: {e.msg} (line {e.lineno})",
                    path=str(py),
                )
            )
        except OSError as e:
            diags.append(
                Diag(
                    severity=Severity.ERROR,
                    code="E_PARSE",
                    message=f"cannot read {py}: {e}",
                    path=str(py),
                )
            )
    return sort_diags(diags)
