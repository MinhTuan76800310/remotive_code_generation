"""Codegen: ValidatedEcaIR → Remotive BM package (__init__/__main__)."""
from __future__ import annotations

import ast
from pathlib import Path

from bmgen_eca.codegen import write_artifacts
from bmgen_eca.diagnostics import has_errors
from bmgen_eca.pipeline import compile_yaml, generate


def test_codegen_syntax_and_shape(schema_v2_path, tmp_path):
    ir, diags = compile_yaml(schema_v2_path)
    assert ir and not has_errors(diags)
    pkg = write_artifacts(ir, tmp_path)
    assert (pkg / "__main__.py").is_file()
    assert (pkg / "__init__.py").is_file()
    assert not (pkg / "log.py").exists()
    assert pkg == tmp_path / "bmgen_generated" / "door_ecu"
    src = (pkg / "__main__.py").read_text()
    ast.parse(src)
    assert "class DoorECU" in src
    assert "DoorECU-BodyCan0" in src
    assert 'FrameFilter("DoorCmd")' in src
    assert "import numpy as np" in src
    assert "np.minimum.reduce" in src or "np.maximum.reduce" in src
    assert "asyncio.sleep(0.2)" in src
    assert 'SenderFilter(ecu_name="DoorECU")' in src
    assert "target_position = frame.signals" in src
    # Remotive live keys are Frame.Signal (no [Bus] prefix)
    assert '["DoorCmd.TargetPosition"]' in src
    assert '["[DoorECU-BodyCan0]DoorCmd.TargetPosition"]' not in src
    assert '("DoorStatus.CurrentPosition"' in src
    assert '("DoorStatus.IsMoving"' in src
    assert '("DoorStatus.IsDone"' in src
    assert "_net(" in src
    assert "self.target_pos = float(" in src
    assert "self.current_pos = float(" in src
    assert "self.door_moving = bool(" in src
    assert "update_signals" in src
    assert "BrokerClient" in src
    assert "run_forever" in src


def test_generate_end_to_end(schema_v2_path, tmp_path):
    pkg, diags = generate(schema_v2_path, tmp_path)
    assert not has_errors(diags)
    assert pkg is not None
    assert pkg == tmp_path / "bmgen_generated" / "door_ecu"
    assert (pkg / "__main__.py").is_file()
