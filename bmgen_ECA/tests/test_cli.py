"""CLI: errors / generate / verify."""
from __future__ import annotations

import ast
from pathlib import Path

from bmgen_eca.cli import main


def test_errors_subcommand(capsys):
    assert main(["errors"]) == 0
    out = capsys.readouterr().out
    assert "E_UNRESOLVED_IDENT" in out
    assert "E_BARE_IDENT" in out


def test_generate_e2e(schema_v2_path, tmp_path, capsys):
    rc = main(["generate", str(schema_v2_path), "--out", str(tmp_path)])
    assert rc == 0
    main_py = tmp_path / "bmgen_generated" / "door_ecu" / "__main__.py"
    assert main_py.is_file()
    ast.parse(main_py.read_text())
    out = capsys.readouterr().out
    assert "wrote" in out
    assert "door_ecu" in out


def test_generate_red_no_write(schema_v2_path, tmp_path):
    text = schema_v2_path.read_text()
    block = (
        "    - name: target_pos\n"
        "      type: float\n"
        "      init: 0.0\n"
    )
    assert block in text
    bad = tmp_path / "bad.yaml"
    bad.write_text(text.replace(block, ""))
    out_dir = tmp_path / "out"
    rc = main(["generate", str(bad), "--out", str(out_dir)])
    assert rc == 1
    assert not (out_dir / "bmgen_generated").exists()


def test_verify_generated_ok(schema_v2_path, tmp_path):
    assert main(["generate", str(schema_v2_path), "--out", str(tmp_path)]) == 0
    pkg = tmp_path / "bmgen_generated" / "door_ecu"
    assert main(["verify", str(pkg)]) == 0


def test_parse_green(schema_v2_path):
    assert main(["parse", str(schema_v2_path)]) == 0


def test_parse_red(schema_v2_path, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "apiVersion: v1.0\n"
        "behavior:\n"
        "  interfaces: {can_rx: [], can_tx: [], someip_tx: []}\n"
        "  parameters: []\n"
        "  state: []\n"
        "  timers: []\n"
        "  rules: []\n"
    )
    assert main(["parse", str(bad)]) == 1
