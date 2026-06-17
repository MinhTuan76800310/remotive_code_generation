"""Tests for verification of generated code."""

import os

import pytest

from bmgen.compiler.context_builder import build_template_context
from bmgen.compiler.python_generator import generate
from bmgen.ir.builder import build_ir
from bmgen.ir.parser import parse_yaml_string
from bmgen.recipes.registry import create_default_registry
from bmgen.verifier.composition import run_composition_checks
from bmgen.verifier.report import VerificationReport
from bmgen.verifier.runner import run_verification
from bmgen.verifier.structural import run_structural_checks


class TestStructuralVerification:
    """Test T1 structural verifier on generated code."""

    def test_t1_file_exists_pass(self, bcm_direct_yaml, temp_output_dir):
        """T1 file_exists check passes when generated file exists."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        report = VerificationReport()
        result = run_structural_checks(temp_output_dir, ir, report)

        # Check that file_exists passed
        file_exists_checks = [c for c in report.checks if c.name == "file_exists"]
        assert len(file_exists_checks) == 1
        assert file_exists_checks[0].status == "PASS"

    def test_t1_syntax_valid_pass(self, bcm_direct_yaml, temp_output_dir):
        """T1 syntax_valid check passes for generated code."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        report = VerificationReport()
        run_structural_checks(temp_output_dir, ir, report)

        syntax_checks = [c for c in report.checks if c.name == "syntax_valid"]
        assert len(syntax_checks) == 1
        assert syntax_checks[0].status == "PASS"

    def test_t1_handler_async_pass(self, bcm_direct_yaml, temp_output_dir):
        """T1 handler_async check passes — handlers are async."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        report = VerificationReport()
        run_structural_checks(temp_output_dir, ir, report)

        async_checks = [c for c in report.checks if c.name == "handler_async"]
        assert len(async_checks) == 1
        assert async_checks[0].status == "PASS"

    def test_t1_handler_accepts_frame_pass(self, bcm_direct_yaml, temp_output_dir):
        """T1 handler_accepts_frame check passes."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        report = VerificationReport()
        run_structural_checks(temp_output_dir, ir, report)

        frame_checks = [c for c in report.checks if c.name == "handler_accepts_frame"]
        assert len(frame_checks) == 1
        assert frame_checks[0].status == "PASS"

    def test_t1_namespace_refs_pass(self, bcm_direct_yaml, temp_output_dir):
        """T1 namespace_refs_exist check passes."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        report = VerificationReport()
        run_structural_checks(temp_output_dir, ir, report)

        ns_checks = [c for c in report.checks if c.name == "namespace_refs_exist"]
        assert len(ns_checks) == 1
        assert ns_checks[0].status == "PASS"

    def test_t1_output_has_restbus_pass(self, bcm_direct_yaml, temp_output_dir):
        """T1 output_has_restbus check passes."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        report = VerificationReport()
        run_structural_checks(temp_output_dir, ir, report)

        restbus_checks = [c for c in report.checks if c.name == "output_has_restbus"]
        assert len(restbus_checks) == 1
        assert restbus_checks[0].status == "PASS"

    def test_t1_frame_filter_pass(self, bcm_direct_yaml, temp_output_dir):
        """T1 input_has_frame_filter check passes."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        report = VerificationReport()
        run_structural_checks(temp_output_dir, ir, report)

        ff_checks = [c for c in report.checks if c.name == "input_has_frame_filter"]
        assert len(ff_checks) == 1
        assert ff_checks[0].status == "PASS"

    def test_t1_main_function_pass(self, bcm_direct_yaml, temp_output_dir):
        """T1 main_function_exists check passes."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        report = VerificationReport()
        run_structural_checks(temp_output_dir, ir, report)

        main_checks = [c for c in report.checks if c.name == "main_function_exists"]
        assert len(main_checks) == 1
        assert main_checks[0].status == "PASS"

    def test_t1_entry_point_pass(self, bcm_direct_yaml, temp_output_dir):
        """T1 entry_point_exists check passes."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        report = VerificationReport()
        run_structural_checks(temp_output_dir, ir, report)

        entry_checks = [c for c in report.checks if c.name == "entry_point_exists"]
        assert len(entry_checks) == 1
        assert entry_checks[0].status == "PASS"


class TestCompositionVerification:
    """Test T3 composition verifier on valid IR."""

    def test_t3_no_duplicate_handlers_pass(self, bcm_direct_ir):
        """T3 no_duplicate_handler_names passes."""
        report = VerificationReport()
        run_composition_checks(bcm_direct_ir, report)

        dup_checks = [c for c in report.checks if c.name == "no_duplicate_handler_names"]
        assert len(dup_checks) == 1
        assert dup_checks[0].status == "PASS"

    def test_t3_no_pattern_conflicts_pass(self, bcm_direct_ir):
        """T3 no_pattern_conflicts passes."""
        report = VerificationReport()
        run_composition_checks(bcm_direct_ir, report)

        conflict_checks = [c for c in report.checks if c.name == "no_pattern_conflicts"]
        assert len(conflict_checks) == 1
        assert conflict_checks[0].status == "PASS"

    def test_t3_toggle_model_composition_pass(self, bcm_toggle_ir):
        """T3 composition passes for ToggleButtonState model."""
        report = VerificationReport()
        run_composition_checks(bcm_toggle_ir, report)

        # Check that reset coverage passes
        reset_checks = [c for c in report.checks if c.name == "reset_covered_all_owned_states"]
        assert any(c.status == "PASS" for c in reset_checks)


class TestEndToEndVerification:
    """Test end-to-end verification pipeline (T1 → T2 → T3)."""

    def test_full_verification_pipeline(self, bcm_direct_yaml, temp_output_dir):
        """Full verification pipeline runs on generated DirectSignalMapping code."""
        spec = parse_yaml_string(bcm_direct_yaml)
        ir = build_ir(spec)
        registry = create_default_registry()
        context = build_template_context(ir, registry)
        generate(context, temp_output_dir)

        report = run_verification(temp_output_dir, ir)

        # Overall should be PASS (or have SKIP for behavioral dynamic checks)
        # T1 should pass (PASS or SKIP for module_imports which requires remotivelabs packages)
        t1_checks = [c for c in report.checks if c.layer == "structural"]
        assert all(c.status in ("PASS", "SKIP") for c in t1_checks)
