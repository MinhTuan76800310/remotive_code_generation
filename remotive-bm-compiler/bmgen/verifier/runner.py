"""Verification runner — orchestrates T1 → T2 → T3 in sequence.

The runner executes verification layers in order: T1 first, then T2, then T3.
If T1 fails, T2 and T3 are not run. If T2 fails, T3 is not run.
This fail-fast design prevents wasting time on behavioral or composition
checks when the code is structurally broken.
"""

from __future__ import annotations

import json

from bmgen.ir.model import BehavioralModelIR
from bmgen.verifier.behavioral import run_behavioral_checks
from bmgen.verifier.composition import run_composition_checks
from bmgen.verifier.report import VerificationReport
from bmgen.verifier.structural import run_structural_checks


def run_verification(
    generated_dir: str,
    ir: BehavioralModelIR,
) -> VerificationReport:
    """Run all verification layers (T1 → T2 → T3) on generated code.

    Args:
        generated_dir: Path to the directory containing generated Python files.
        ir: The BehavioralModelIR that was used to generate the code.

    Returns:
        Complete VerificationReport with all check results.
    """
    report = VerificationReport()

    # T1: Structural verification
    t1_pass = run_structural_checks(generated_dir, ir, report)
    if not t1_pass:
        # T1 failed — skip T2 and T3
        report.add_check("behavioral", "behavioral_checks", "SKIP",
                         "Skipped because T1 structural checks failed")
        report.add_check("composition", "composition_checks", "SKIP",
                         "Skipped because T1 structural checks failed")
        return report

    # T2: Behavioral verification
    t2_pass = run_behavioral_checks(generated_dir, ir, report)
    if not t2_pass:
        # T2 failed — skip T3
        report.add_check("composition", "composition_checks", "SKIP",
                         "Skipped because T2 behavioral checks failed")
        return report

    # T3: Composition verification
    t3_pass = run_composition_checks(ir, report)

    return report


def format_report_json(report: VerificationReport) -> str:
    """Format the verification report as JSON."""
    return json.dumps(report.to_dict(), indent=2)
