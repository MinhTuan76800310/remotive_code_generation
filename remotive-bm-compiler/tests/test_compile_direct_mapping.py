"""Tests for DirectSignalMapping code generation end-to-end."""

import os

import pytest

from bmgen.compiler.context_builder import build_template_context
from bmgen.compiler.python_generator import generate
from bmgen.ir.builder import build_ir
from bmgen.ir.parser import parse_yaml_string
from bmgen.recipes.registry import create_default_registry


class TestDirectSignalMappingGeneration:
    """Test end-to-end code generation for DirectSignalMapping pattern."""

    def test_generate_direct_mapping_produces_files(self, bcm_direct_yaml, temp_output_dir):
        """Generated code produces __main__.py, __init__.py, and log.py."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        files = generate(context, temp_output_dir)

        assert len(files) == 3
        assert any("__main__.py" in f for f in files)
        assert any("__init__.py" in f for f in files)
        assert any("log.py" in f for f in files)

    def test_generated_main_py_is_valid_python(self, bcm_direct_yaml, temp_output_dir):
        """Generated __main__.py is syntactically valid Python."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "bcm", "__main__.py")
        assert os.path.isfile(main_path)

        with open(main_path) as f:
            content = f.read()

        # Check syntax validity
        import ast
        ast.parse(content)  # Should not raise SyntaxError

    def test_generated_code_has_handler_method(self, bcm_direct_yaml, temp_output_dir):
        """Generated code contains the on_hazard_light handler method."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "bcm", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        assert "async def on_hazard_light" in content
        assert "frame: Frame" in content
        assert "frame.signals" in content
        assert "restbus.update_signals" in content

    def test_generated_code_has_namespace_setup(self, bcm_direct_yaml, temp_output_dir):
        """Generated code sets up CanNamespace objects correctly."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "bcm", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        assert "BCM-BodyCan0" in content
        assert "BCM-DriverCan0" in content
        assert "RestbusConfig" in content
        assert "SenderFilter" in content

    def test_generated_code_has_frame_filter(self, bcm_direct_yaml, temp_output_dir):
        """Generated code has FrameFilter for input handler."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "bcm", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        assert 'FrameFilter("HazardLightButton")' in content

    def test_generated_code_has_main_function(self, bcm_direct_yaml, temp_output_dir):
        """Generated code has the async main() function."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "bcm", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        assert "async def main(avp: BehavioralModelArgs)" in content
        assert "if __name__" in content and "__main__" in content
        assert "BehavioralModelArgs.parse()" in content

    def test_generated_code_output_signals(self, bcm_direct_yaml, temp_output_dir):
        """Generated code writes to the correct output signals."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "bcm", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        assert "TurnLightControl.RightTurnLightRequest" in content
        assert "TurnLightControl.LeftTurnLightRequest" in content


class TestToggleButtonStateGeneration:
    """Test end-to-end code generation for ToggleButtonState pattern."""

    def test_generate_toggle_produces_files(self, bcm_toggle_yaml, temp_output_dir):
        """Generated code produces files for toggle model."""
        spec = parse_yaml_string(bcm_toggle_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        files = generate(context, temp_output_dir)

        assert len(files) == 3

    def test_generated_toggle_has_state(self, bcm_toggle_yaml, temp_output_dir):
        """Generated code has state variable and toggle logic."""
        spec = parse_yaml_string(bcm_toggle_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "bcm", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        assert "_hazard_enabled" in content
        assert "not self._hazard_enabled" in content

    def test_generated_toggle_has_reset_handler(self, bcm_toggle_yaml, temp_output_dir):
        """Generated code has on_reboot reset handler."""
        spec = parse_yaml_string(bcm_toggle_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        main_path = os.path.join(temp_output_dir, "bcm", "__main__.py")
        with open(main_path) as f:
            content = f.read()

        assert "on_reboot" in content
        assert "restbus.reset()" in content
