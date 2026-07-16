"""Pipeline E2E via generate + verify_package."""
from __future__ import annotations

import ast

from bmgen_eca.diagnostics import has_errors
from bmgen_eca.pipeline import generate
from bmgen_eca.verify import verify_package


def test_generate_and_verify(schema_v2_path, tmp_path):
    pkg, diags = generate(schema_v2_path, tmp_path)
    assert pkg is not None
    assert not has_errors(diags)
    assert pkg == tmp_path / "bmgen_generated" / "door_ecu"
    main_py = pkg / "__main__.py"
    assert main_py.is_file()
    ast.parse(main_py.read_text())
    vdiags = verify_package(pkg)
    assert not has_errors(vdiags)


def test_generate_no_write_on_error(schema_v2_path, tmp_path):
    text = schema_v2_path.read_text()
    block = (
        "    - name: target_pos\n"
        "      type: float\n"
        "      init: 0.0\n"
    )
    bad = tmp_path / "bad.yaml"
    bad.write_text(text.replace(block, ""))
    out = tmp_path / "out"
    pkg, diags = generate(bad, out)
    assert pkg is None
    assert has_errors(diags)
    assert any(d.code == "E_UNRESOLVED_IDENT" for d in diags)
    assert not (out / "bmgen_generated").exists()
