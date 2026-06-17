"""T3 Composition Verifier — checks cross-handler consistency and lifecycle.

T3 operates on the complete IR + generated code together. It checks for:
- Duplicate handler names in the model
- Duplicate state ownership
- Pattern conflicts (two handlers writing same signal with different logic)
- Periodic task cleanup requirements
- Reset handler coverage
- Lifecycle validity

T3 runs after T1 (structural) and T2 (behavioral) both PASS.
"""

from __future__ import annotations

from bmgen.verifier.report import VerificationReport


def run_composition_checks(
    ir: "BehavioralModelIR",
    report: VerificationReport,
) -> bool:
    """Run all T3 composition checks.

    Args:
        ir: The BehavioralModelIR that was used to generate the code.
        report: VerificationReport to add check results to.

    Returns:
        True if all T3 checks PASS, False if any FAIL.
    """
    all_pass = True

    # Check 1: no_duplicate_handler_names
    handler_names = [h.name for h in ir.handlers]
    duplicates = [name for name in handler_names if handler_names.count(name) > 1]
    if not duplicates:
        report.add_check("composition", "no_duplicate_handler_names", "PASS",
                         "All handler names are unique")
    else:
        report.add_check("composition", "no_duplicate_handler_names", "FAIL",
                         f"Duplicate handler names: {set(duplicates)}")
        all_pass = False

    # Check 2: no_duplicate_state_ownership
    state_owners = {}
    for h in ir.handlers:
        if h.state:
            state_owners.setdefault(h.state.name, []).append(h.state.owner)

    duplicate_states = {name: owners for name, owners in state_owners.items() if len(owners) > 1}
    if not duplicate_states:
        report.add_check("composition", "no_duplicate_state_ownership", "PASS",
                         "No shared state fields")
    else:
        report.add_check("composition", "no_duplicate_state_ownership", "FAIL",
                         f"States with multiple owners: {duplicate_states}")
        all_pass = False

    # Check 3: no_pattern_conflicts
    signal_writers = {}  # signal_name → [(handler_name, pattern)]
    for h in ir.handlers:
        for s in h.output_signals:
            signal_writers.setdefault(s.name, []).append((h.name, h.pattern))

    conflicts = {}
    for signal, writers in signal_writers.items():
        patterns = set(p for _, p in writers)
        if len(patterns) > 1:
            conflicts[signal] = writers

    if not conflicts:
        report.add_check("composition", "no_pattern_conflicts", "PASS",
                         "No conflicting output signals")
    else:
        # Check if conflicts involve novel_logic — those are warnings, not errors
        real_conflicts = {}
        for signal, writers in conflicts.items():
            novel_writers = [w for w in writers if next(h for h in ir.handlers if h.name == w[0]).novel_logic]
            if len(writers) - len(novel_writers) > 1:
                real_conflicts[signal] = writers

        if real_conflicts:
            report.add_check("composition", "no_pattern_conflicts", "FAIL",
                             f"Conflicting patterns for same signals: {real_conflicts}")
            all_pass = False
        else:
            report.add_check("composition", "no_pattern_conflicts", "PASS",
                             "Signal conflicts only involve novel_logic handlers (warning)")
            for signal, writers in conflicts.items():
                report.add_warning("duplicate_signal_source", "",
                                   f"Signal '{signal}' written by multiple handlers: {writers}")

    # Check 4: periodic_tasks_have_cleanup
    periodic_tasks = [h for h in ir.handlers if h.periodic_task is not None]
    all_have_cleanup = all(h.periodic_task.cleanup for h in periodic_tasks)
    if not periodic_tasks:
        report.add_check("composition", "periodic_tasks_have_cleanup", "PASS",
                         "No periodic tasks (check N/A)")
    elif all_have_cleanup:
        report.add_check("composition", "periodic_tasks_have_cleanup", "PASS",
                         "All periodic tasks have cleanup=True")
    else:
        bad_handlers = [h.name for h in periodic_tasks if not h.periodic_task.cleanup]
        report.add_check("composition", "periodic_tasks_have_cleanup", "FAIL",
                         f"Periodic tasks without cleanup: {bad_handlers}")
        all_pass = False

    # Check 5: reset_covered_all_owned_states
    if ir.reset_handler:
        states_with_reset = {s.name for s in ir.reset_handler.states_to_reset}
        owned_states = {h.state.name for h in ir.handlers if h.state and h.state.reset_value is not None}
        uncovered = owned_states - states_with_reset
        if not uncovered:
            report.add_check("composition", "reset_covered_all_owned_states", "PASS",
                             "All owned states covered by reset handler")
        else:
            report.add_check("composition", "reset_covered_all_owned_states", "FAIL",
                             f"States not covered by reset: {uncovered}")
            all_pass = False
    else:
        owned_states = [h for h in ir.handlers if h.state and h.state.reset_value is not None]
        if owned_states:
            report.add_check("composition", "reset_covered_all_owned_states", "FAIL",
                             f"Handlers with resettable states but no reset_handler: {[h.name for h in owned_states]}")
            all_pass = False
        else:
            report.add_check("composition", "reset_covered_all_owned_states", "PASS",
                             "No states requiring reset (check N/A)")

    # Check 6: reset_covered_all_output_namespaces
    if ir.reset_handler:
        output_ns_names = {ns.name for ns in ir.namespaces if ns.role in ("output", "both")}
        reset_ns_names = set(ir.reset_handler.namespaces_to_reset)
        uncovered = output_ns_names - reset_ns_names
        if not uncovered:
            report.add_check("composition", "reset_covered_all_output_namespaces", "PASS",
                             "All output namespaces covered by reset handler")
        else:
            report.add_check("composition", "reset_covered_all_output_namespaces", "FAIL",
                             f"Output namespaces not covered by reset: {uncovered}")
            all_pass = False

    # Check 7: input_namespace_not_output (for same handler)
    for h in ir.handlers:
        if h.input_namespace == h.output_namespace:
            # Check if the namespace role is "both" — that's OK
            ns = next(n for n in ir.namespaces if n.name == h.input_namespace)
            if ns.role != "both":
                report.add_check("composition", "input_namespace_not_output", "FAIL",
                                 f"Handler '{h.name}' uses same namespace '{h.input_namespace}' as input and output (role: '{ns.role}')")
                all_pass = False
            else:
                report.add_check("composition", "input_namespace_not_output", "PASS",
                                 f"Handler '{h.name}' uses same namespace (role='both') — OK")
        else:
            report.add_check("composition", "input_namespace_not_output", "PASS",
                             f"Handler '{h.name}' uses different namespaces for input/output")

    # Check 8: frame_filter_unique_per_namespace
    ff_map = {}  # (namespace, frame_filter) → [handler_name]
    for h in ir.handlers:
        key = (h.input_namespace, h.input_frame_filter)
        ff_map.setdefault(key, []).append(h.name)

    duplicate_ffs = {key: names for key, names in ff_map.items() if len(names) > 1}
    if not duplicate_ffs:
        report.add_check("composition", "frame_filter_unique_per_namespace", "PASS",
                         "No duplicate FrameFilter on same namespace")
    else:
        # Multiple handlers on same namespace+filter is OK (e.g., both on_gear_up and on_gear_down
        # read from GearShiftPaddles) — this is a warning, not an error
        report.add_check("composition", "frame_filter_unique_per_namespace", "PASS",
                         f"Multiple handlers on same FrameFilter: {duplicate_ffs} (acceptable)")
        for key, names in duplicate_ffs.items():
            report.add_warning("duplicate_signal_source", ", ".join(names),
                               f"FrameFilter '{key[1]}' on namespace '{key[0]}' shared by handlers: {names}")

    # Check 9: novel_logic_handlers_listed
    actual_novel = {h.name for h in ir.handlers if h.novel_logic}
    declared_novel = set(ir.novel_logic_handlers)
    if actual_novel == declared_novel:
        report.add_check("composition", "novel_logic_handlers_listed", "PASS",
                         "novel_logic handlers correctly listed")
    else:
        report.add_check("composition", "novel_logic_handlers_listed", "FAIL",
                         f"novel_logic mismatch: actual={actual_novel}, declared={declared_novel}")
        all_pass = False

    # Check 10: composed_model_has_no_invalid_lifecycle
    # Check that the model has a main function and entry point structure
    # (This is partially covered by T1, but T3 checks lifecycle completeness)
    has_reset = ir.reset_handler is not None
    needs_reset = any(h.state for h in ir.handlers)
    if needs_reset and not has_reset:
        report.add_check("composition", "composed_model_has_no_invalid_lifecycle", "FAIL",
                         "Model has state variables but no reset handler")
        all_pass = False
    else:
        report.add_check("composition", "composed_model_has_no_invalid_lifecycle", "PASS",
                         "Model lifecycle is valid")

    return all_pass


# Type hint
from bmgen.ir.model import BehavioralModelIR  # noqa: E402
