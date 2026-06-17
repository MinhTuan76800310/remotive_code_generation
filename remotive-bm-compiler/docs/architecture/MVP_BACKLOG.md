# MVP Backlog — Remotive Behavioral Model Compiler

## Priority Definitions

| Priority | Label | Meaning |
|----------|-------|---------|
| **P0** | MVP | Must be complete before the first release. Blocks all other work. |
| **P1** | MVP+ | Strongly desired for first release, but not a hard blocker. Can ship without if schedule demands. |
| **P2** | Future | Planned for later releases. Architectural decisions in P0/P1 should not block these, but no implementation yet. |
| **P3** | Exploration | Research/spike only. May never become a ticket. |

---

## P0 — MVP (Must Ship)

### BMG-001: Create repository structure and package skeleton

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Set up the `remotive-bm-compiler` repository with directories, `pyproject.toml`, `__init__.py` files, and `bmgen` CLI entry point |
| **Description** | The package structure defines the boundary between IR, recipes, compiler, verifier, and CLI. Getting this right early prevents circular dependencies. |
| **Tasks** | 1. Create `bmgen/{ir,recipes,compiler/templates,verifier,config}` directories 2. Write `pyproject.toml` with dependencies (`pyyaml`, `jinja2`, `structlog`) and dev deps (`pytest`, `pytest-asyncio`, `ruff`, `mypy`) 3. Add `__init__.py` to each package 4. Register `bmgen` CLI entry point in `pyproject.toml` 5. Add `README.md` |
| **Acceptance** | `pip install -e ".[dev]"` succeeds and `bmgen` command is available |

---

### BMG-002: Define typed IR dataclasses

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Implement all IR dataclass definitions in `bmgen/ir/model.py` |
| **Description** | The IR is the machine-facing representation between YAML and the compiler. It must enforce structural correctness (required fields, types, cross-references) while validators enforce semantic correctness. |
| **Tasks** | 1. Define `BehavioralModelIR` (name, ecu_name, namespaces, handlers, reset_handler, novel_logic_handlers) 2. Define `NamespaceIR` (name, type, role, restbus, python_var_name) 3. Define `RestbusConfigIR` (sender_filter) 4. Define `HandlerIR` (name, pattern, novel_logic, input/output signals, state, periodic_task) 5. Define `InputSignalIR` and `OutputSignalIR` (name, python_var_name, value_expr) 6. Define `StateIR` (name, type, initial, reset_value, owner) 7. Define `PeriodicTaskIR` (interval_sec, blink_output_namespace, blink_output_signals, cleanup) 8. Define `ResetHandlerIR` (states_to_reset, namespaces_to_reset) 9. Implement `_derive_python_var_name()` for namespace→snake_case conversion 10. Implement `_derive_signal_var_name()` for signal→snake_case conversion |
| **Acceptance** | All IR dataclasses instantiate correctly. `BCM-BodyCan0` → `body_can_0`. `HazardLightButton.HazardLightButton` → `hazard_light_button_signal` |

---

### BMG-003: Implement IR invariant validators

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Implement all 10 IR invariant validation checks in `bmgen/ir/validators.py` |
| **Description** | Validators catch semantic errors that dataclass types cannot enforce: uniqueness, cross-reference existence, pattern compatibility, and novel_logic consistency. |
| **Tasks** | 1. `namespace_names_unique` — no duplicate namespace names 2. `handler_names_unique` — no duplicate handler names 3. `handler_input_namespace_exists` — input namespace must reference existing namespace 4. `handler_output_namespace_exists` — output namespace must reference existing namespace 5. `output_namespace_has_restbus` — output namespace must have restbus config and role "output"/"both" 6. `state_single_owner` — each state has exactly one owner 7. `periodic_task_has_cleanup` — periodic tasks must declare cleanup=True 8. `resettable_state_has_reset_value` — toggle/blink states must have reset_value 9. `unknown_pattern_fails_early` — unknown pattern must be marked novel_logic or fail 10. `novel_logic_handlers_listed` — novel_logic handlers must be listed in BehavioralModelIR |
| **Acceptance** | All 10 invariants produce `ValidationViolation` objects. `has_errors()` correctly identifies severity="error". Valid spec produces 0 violations. Invalid spec produces violations with correct messages. |

---

### BMG-004: Implement YAML parser and IR builder

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Parse YAML spec files into raw dicts and build validated BehavioralModelIR |
| **Description** | The parser reads YAML text → Python dict (no validation). The builder converts the dict → IR dataclasses → runs validators → applies recipe-derived value_exprs. This is the bridge between the user-facing YAML format and the machine-facing IR. |
| **Tasks** | 1. Implement `parse_yaml_file()` and `parse_yaml_string()` in `parser.py` 2. Implement `build_ir()` in `builder.py` — extracts model/namespaces/handlers from raw dict, constructs IR dataclasses, runs validators 3. Implement `_build_namespaces()`, `_build_handlers()`, `_build_reset_handler()` helper functions 4. Implement `_apply_value_exprs()` — fills in `OutputSignalIR.value_expr` based on recipe pattern 5. Define `BuilderError` exception class for validation failures |
| **Acceptance** | `build_ir(parse_yaml_file("examples/bcm_direct.yaml"))` returns a valid `BehavioralModelIR` with no violations. Invalid YAML raises `BuilderError` with violation details. |

---

### BMG-005: Write example YAML specs

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Create `bcm_direct.yaml`, `bcm_toggle.yaml`, and `bcm_blinking.yaml` example specs |
| **Description** | Example specs serve as both documentation and test inputs. They must cover all P0 patterns and validate against the IR schema. |
| **Tasks** | 1. Write `examples/bcm_direct.yaml` — DirectSignalMapping (hazard light → both turn lights) 2. Write `examples/bcm_toggle.yaml` — ToggleButtonState (hazard button toggle) 3. Write `examples/bcm_blinking.yaml` — combined DirectSignalMapping + PeriodicBlinkingOutput (P1 pattern) |
| **Acceptance** | All 3 YAML files parse successfully through `bmgen parse`. `bcm_direct.yaml` and `bcm_toggle.yaml` produce valid IR with no violations. |

---

### BMG-006: Implement recipe registry and DirectSignalMapping recipe

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Create flat recipe registry and implement the DirectSignalMapping pattern |
| **Description** | The recipe registry is a simple dict mapping pattern names → Recipe instances. DirectSignalMapping is the simplest pattern: read one signal, forward same value to outputs via `restbus.update_signals`. |
| **Tasks** | 1. Define `Recipe` abstract base class in `base.py` with `name`, `description`, `template_name`, `validate()`, `build_context()` methods 2. Define `RecipeContext` dataclass (handler_name, pattern, template_name, context dict) 3. Implement `RecipeRegistry` in `registry.py` — flat dict with `register()`, `get()`, `list_all()`, `known_patterns()` 4. Implement `DirectSignalMappingRecipe` — validate (1 input, ≥1 output, no state, no periodic), build context (input_signal_var, output_tuples) 5. Implement `create_default_registry()` — registers all MVP recipes |
| **Acceptance** | `registry.get("DirectSignalMapping")` returns recipe. `recipe.validate(handler_ir)` returns empty list for valid DirectSignalMapping handler. `recipe.build_context(handler_ir)` produces context with `output_tuples`, `input_signal_var`, `input_signal_ref`. |

---

### BMG-007: Implement Jinja2 templates for DirectSignalMapping

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Create `main.py.j2` and `handler_direct.py.j2` Jinja2 templates |
| **Description** | Templates are the deterministic code generation engine. No LLM — same context always produces same output. The main template generates the complete behavioral model file (imports, class, handlers, main function, entry point). Handler templates are rendered separately and injected into the main template. |
| **Tasks** | 1. Write `main.py.j2` — imports, class definition, namespace fields, state fields, handler body injection, main function, BehavioralModel setup, input_handlers list, entry point 2. Write `handler_direct.py.j2` — async handler method, frame.signals extraction, restbus.update_signals call with tuples 3. Write `handler_reset.py.j2` — on_reboot handler that resets states and calls restbus.reset() 4. Handle conditional imports (RebootRequest, ControlRequest/ControlResponse when has_reset_handler) 5. Handle class type switch (@dataclass for no-state models, plain class for state models) |
| **Acceptance** | Rendering `main.py.j2` with DirectSignalMapping context produces syntactically valid Python that matches the getting_started BCM reference example structure. Handler body is correctly indented inside the class. |

---

### BMG-008: Implement Python code generator and context builder

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Build the `python_generator.py` (template rendering + file writing) and `context_builder.py` (IR + recipes → unified template context) |
| **Description** | The context builder merges IR data and recipe-produced contexts into a single Jinja2 template dict. The generator pre-renders handler templates separately (avoiding Jinja2 include scoping issues), then renders the main template with pre-rendered handler bodies. It also generates __init__.py and log.py. |
| **Tasks** | 1. Implement `build_template_context()` — model-level, namespace, handler, state, reset handler contexts 2. Implement `_merge_recipe_context()` — flatten recipe context into handler dict with namespace var lookups 3. Implement `_build_novel_logic_context()` — stub handler context for unknown patterns 4. Implement `generate()` — pre-render handler templates, indent handler bodies (4 spaces for class), render main template, write files 5. Implement `_indent_body()` — add 4-space indentation to multi-line handler body strings 6. Generate __init__.py (empty) and log.py (structlog config) |
| **Acceptance** | `bmgen generate examples/bcm_direct.yaml --out /tmp/gen/` produces 3 files. Generated __main__.py is syntactically valid Python with correct Remotive API patterns. |

---

### BMG-009: Implement ToggleButtonState recipe and template

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Add ToggleButtonState recipe to registry and create handler_toggle.py.j2 template |
| **Description** | ToggleButtonState reads a button signal, tracks previous state to detect "presses" (0→non-zero transition), toggles a boolean state variable, and writes 1/0 to output signals based on the toggled state. It also needs `previous_state_var` tracking and a reset handler. |
| **Tasks** | 1. Implement `ToggleButtonStateRecipe` — validate (1 input, ≥1 output, bool state with reset_value), build context (state_private_var, previous_state_var, value_exprs) 2. Write `handler_toggle.py.j2` — async handler with if-check on previous state, toggle logic, update_signals with `1 if self._state else 0` 3. Register in `create_default_registry()` |
| **Acceptance** | `bmgen generate examples/bcm_toggle.yaml --out /tmp/gen/` produces code with toggle logic. Press once → enabled, press again → disabled. Reset handler resets state to False and calls restbus.reset(). |

---

### BMG-010: Implement T1 structural verifier

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Implement all T1 structural checks in `bmgen/verifier/structural.py` |
| **Description** | T1 checks generated code as static artifacts — syntax, AST structure, import presence, handler signatures, namespace references. T1 must PASS before T2 runs. |
| **Tasks** | 1. `file_exists` — generated Python file exists 2. `syntax_valid` — Python syntax is valid (ast.parse) 3. `remotive_imports_present` — all required Remotive imports found 4. `handler_async` — handler methods are `async def` 5. `handler_accepts_frame` — handler methods accept `frame: Frame` parameter 6. `namespace_refs_exist` — namespace string literals match IR names 7. `output_has_restbus` — output namespace has `restbus_configs` argument 8. `input_has_frame_filter` — FrameFilter strings match IR specs 9. `restbus_update_signals_used` — handler body contains update_signals call 10. `main_function_exists` — async def main exists 11. `entry_point_exists` — `if __name__ == "__main__"` block exists 12. `module_imports` — SKIP in test env (requires remotivelabs packages) |
| **Acceptance** | All T1 checks produce PASS for generated DirectSignalMapping and ToggleButtonState code. Invalid code produces FAIL with descriptive messages. |

---

### BMG-011: Implement T2 behavioral verifier (AST-based fallback)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Implement T2 behavioral checks with AST-based fallback when remotivelabs packages unavailable |
| **Description** | T2 verifies handler behavior. In production (with remotivelabs packages installed), it dynamically loads the module, creates FakeFrame and MockRestbus, calls handlers, and checks output. In test/dev environments without remotivelabs, it falls back to AST-based verification (handler exists, signal references found). Dynamic behavioral verification is P1 (BMG-018). |
| **Tasks** | 1. Implement `FakeFrame` — dict-based signal mock 2. Implement `MockRestbus` — captures update_signals calls 3. Implement `MockNamespace` — namespace with mock restbus 4. Implement dynamic verification path (module import + handler call) 5. Implement AST-based fallback path (handler existence, signal reference checks) 6. Implement DirectSignalMapping behavioral check (output signals match input value) 7. Implement ToggleButtonState behavioral check (press once→enabled, press twice→disabled) 8. novel_logic handlers: SKIP behavioral checks, add warning |
| **Acceptance** | T2 produces PASS or SKIP for generated code. AST fallback works without remotivelabs packages. Dynamic path works when remotivelabs is installed. |

---

### BMG-012: Implement T3 composition verifier

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Implement all T3 composition checks in `bmgen/verifier/composition.py` |
| **Description** | T3 checks cross-handler consistency, lifecycle completeness, and pattern compatibility. It operates on the IR (not generated files) and verifies that the composed model has no systemic conflicts. |
| **Tasks** | 1. `no_duplicate_handler_names` — unique handler names 2. `no_duplicate_state_ownership` — each state has one owner 3. `no_pattern_conflicts` — no conflicting logic for same output signal 4. `periodic_tasks_have_cleanup` — all periodic tasks have cleanup=True 5. `reset_covered_all_owned_states` — reset handler covers all states with reset_value 6. `reset_covered_all_output_namespaces` — reset handler covers all output namespaces 7. `input_namespace_not_output` — handler doesn't use same namespace for both (unless role="both") 8. `frame_filter_unique_per_namespace` — no duplicate FrameFilter on same namespace (warning for shared) 9. `novel_logic_handlers_listed` — novel_logic handlers correctly listed 10. `composed_model_has_no_invalid_lifecycle` — model has reset handler if it has state |
| **Acceptance** | T3 produces PASS for valid IR. Invalid IR produces FAIL for specific composition issues. |

---

### BMG-013: Implement verification report and runner

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Implement `VerificationReport` dataclass and `runner.py` (T1→T2→T3 orchestration) |
| **Description** | The report aggregates all check results into JSON. The runner orchestrates T1→T2→T3 in sequence, fail-fast on any layer failure. |
| **Tasks** | 1. Define `CheckResult` dataclass (layer, name, status, message) 2. Define `VerificationReport` dataclass (status, checks, generated_files, errors, warnings) 3. Implement `add_check()`, `add_warning()`, `to_dict()` methods 4. Implement `run_verification()` — T1→T2→T3 with fail-fast 5. Implement `format_report_json()` — JSON serialization |
| **Acceptance** | `bmgen verify` produces a JSON report with PASS/FAIL/SKIP status for each check. Report matches the schema defined in VERIFIER_DESIGN.md. |

---

### BMG-014: Implement CLI (`bmgen parse`, `generate`, `verify`, `recipes`)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Implement the `bmgen` CLI with 4 subcommands using argparse |
| **Description** | The CLI is the user-facing interface. It orchestrates the pipeline (parse → generate → verify) but contains no business logic itself. |
| **Tasks** | 1. Implement `bmgen parse <yaml>` — parse YAML, build IR, print to stdout 2. Implement `bmgen parse <yaml> --json` — output as JSON 3. Implement `bmgen generate <yaml> --out <dir>` — full pipeline (parse → build → validate → compile) 4. Implement `bmgen verify <dir> --spec <yaml>` — load IR, run T1→T2→T3 5. Implement `bmgen verify <dir> --json` — output verification report as JSON 6. Implement `bmgen recipes` — list all available patterns 7. Handle `BuilderError` and other exceptions with clear error messages |
| **Acceptance** | All 4 commands work end-to-end. `bmgen generate examples/bcm_direct.yaml --out /tmp/gen/` succeeds. `bmgen verify /tmp/gen/ --spec examples/bcm_direct.yaml` produces PASS report. |

---

### BMG-015: Write P0 test suite

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Write tests for IR validation, code generation, and verification |
| **Description** | Tests ensure deterministic behavior and catch regressions. The suite covers IR invariants, generated code correctness, and verification pipeline. |
| **Tasks** | 1. `test_ir_validation.py` — 15 tests covering all invariants (namespace uniqueness, handler uniqueness, namespace refs, restbus, unknown pattern, novel_logic, derived var names, toggle IR) 2. `test_compile_direct_mapping.py` — 10 tests (file generation, syntax validity, handler method, namespace setup, frame filter, main function, output signals, toggle state, reset handler) 3. `test_verify_generated.py` — 14 tests (T1 structural checks, T3 composition checks, end-to-end pipeline) 4. `conftest.py` — shared fixtures (bcm_direct_yaml, bcm_toggle_yaml, bcm_direct_ir, bcm_toggle_ir, temp_output_dir) |
| **Acceptance** | All 39 tests pass with `pytest tests/`. Tests cover positive and negative cases. |

---

### BMG-016: Set up CI workflow

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Status** | ✅ DONE |
| **Summary** | Create GitHub Actions workflow that runs `bmgen verify` and `pytest` on every push/PR |
| **Description** | CI gates on verification. Generated code that fails verification cannot enter the main branch. |
| **Tasks** | 1. Create `.github/workflows/verify.yml` 2. Steps: checkout → setup Python 3.11 → install bmgen → parse all YAML → generate all models → verify all models → run pytest |
| **Acceptance** | CI workflow runs successfully on push. Failing verification blocks merge. |

---

## P1 — MVP+ (Strongly Desired)

### BMG-017: Implement PeriodicBlinkingOutput recipe and template

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Status** | ✅ DONE (code exists, needs more testing) |
| **Summary** | Add PeriodicBlinkingOutput recipe to registry and create handler_blink.py.j2 template |
| **Description** | PeriodicBlinkingOutput uses internal state to enable/disable a blinking pattern. It starts an asyncio ticker task (`create_ticker`) that toggles output signals at a fixed interval. Cleanup cancels the ticker on exit/reboot. |
| **Tasks** | 1. Implement `PeriodicBlinkingOutputRecipe` — validate (1 input, ≥1 output, bool state with reset_value, periodic task with cleanup=True) 2. Write `handler_blink.py.j2` — enable/disable blinking logic, `_start_blinking_*()` method, `_stop_blinking_*()` method, `_blink_loop_*()` async task 3. Generate class-level ticker variable (`_ticker_<state_name>: asyncio.Task | None = None`) 4. Register in `create_default_registry()` 5. Write behavioral test for blink enable/disable state toggling |
| **Acceptance** | `bmgen generate examples/bcm_blinking.yaml --out /tmp/gen/` produces code with async blink loop. Generated code has start/stop/cleanup methods. `bmgen verify` passes T1 and T3. |

---

### BMG-018: Implement full dynamic T2 behavioral verification

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Status** | Partial (AST fallback works; dynamic path needs remotivelabs packages) |
| **Summary** | Make T2 behavioral verification work with remotivelabs packages installed (dynamic module loading + handler invocation) |
| **Description** | When `remotivelabs.topology` packages are available, T2 should dynamically import the generated module, instantiate the model class with mock namespaces, call handlers with FakeFrame, and verify MockRestbus received expected outputs. This gives true behavioral confidence beyond AST checks. |
| **Tasks** | 1. Fix `_load_module_dynamically()` to handle remotivelabs dependency injection 2. Create mock BrokerClient that provides url/auth without real connection 3. Test DirectSignalMapping dynamic path: FakeFrame with signal=1.0 → update_signals receives correct tuples 4. Test ToggleButtonState dynamic path: press once → outputs=1, press twice → outputs=0 5. Add CI test that runs with remotivelabs packages installed (optional, separate job) |
| **Acceptance** | When remotivelabs packages are installed, T2 produces PASS for DirectSignalMapping and ToggleButtonState behavioral tests. |

---

### BMG-019: Add `bmgen verify --spec` auto-detect and IR caching

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Status** | TODO |
| **Summary** | Allow `bmgen verify` to infer the spec from the generated directory, and cache the IR alongside generated code |
| **Description** | Currently `bmgen verify` requires `--spec` to load the IR. For CI convenience, the generator should write a `_ir_cache.json` alongside the generated code so `bmgen verify` can reconstruct the IR without needing the original YAML. |
| **Tasks** | 1. Modify `python_generator.py` to write `_ir_cache.json` alongside generated files 2. Modify `cli.py` `bmgen verify` to load IR from cache when `--spec` is not provided 3. Add `_infer_ir_from_cache()` helper |
| **Acceptance** | `bmgen verify /tmp/gen/` (without `--spec`) loads IR from cache and runs full verification. |

---

### BMG-020: Add multi-handler DirectSignalMapping tests

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Status** | TODO |
| **Summary** | Test that a single model with multiple DirectSignalMapping handlers generates correctly |
| **Description** | The BCM model in the reference examples has multiple handlers (on_hazard_light, on_brake, on_accelerator). Need a YAML spec with multiple handlers and verify they all generate correctly. |
| **Tasks** | 1. Create `examples/bcm_multi_handler.yaml` with 3 DirectSignalMapping handlers 2. Add test that verifies all handlers appear in generated code 3. Add test that FrameFilter strings are unique per namespace 4. Verify T3 composition checks for multi-handler model |
| **Acceptance** | `bmgen generate examples/bcm_multi_handler.yaml` produces code with 3 handler methods, 3 FrameFilters, and passes T1→T2→T3 verification. |

---

### BMG-021: Add `bmgen parse --json` structured IR output for tooling integration

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Status** | ✅ DONE (basic JSON output exists) |
| **Summary** | Ensure `bmgen parse --json` output matches the IR_SCHEMA.md JSON schema exactly |
| **Description** | The JSON output from `bmgen parse --json` is used by tooling (CI, IDEs, potential MCP server). It must match the defined schema exactly for reliable integration. |
| **Tasks** | 1. Verify JSON output includes all IR fields (namespaces with restbus, handlers with state, novel_logic handlers) 2. Add schema validation test 3. Document the JSON output schema in IR_SCHEMA.md |
| **Acceptance** | `bmgen parse examples/bcm_toggle.yaml --json` produces valid JSON matching IR_SCHEMA.md. |

---

## P2 — Future Work

### BMG-022: SOME/IP namespace handler recipe

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Status** | TODO |
| **Summary** | Add SOME/IP namespace support with `SomeIPNamespace`, `SomeIPEventFilter`, and `notify()` recipe |
| **Description** | The GWM and IHU reference examples use `SomeIPNamespace` with `SomeIPEventFilter` for input and `SomeIPNamespace.notify()` with `SomeIPEvent` for output. This is a fundamentally different namespace type from CAN, requiring its own recipe pattern. |
| **Tasks** | 1. Add `SomeIPNamespace` to namespace type enum 2. Implement `CanToSomeIPBridgeRecipe` — CAN input → SOME/IP output via `notify(SomeIPEvent(...))` 3. Write `handler_someip_bridge.py.j2` template 4. Add `SomeIPNamespace` constructor template (with `client_id`) 5. Add SOME/IP input handler template (with `SomeIPEventFilter`) 6. Create `examples/gwm_can_someip.yaml` example spec 7. Update IR validators for SOME/IP namespace invariants |
| **Acceptance** | `bmgen generate examples/gwm_can_someip.yaml` produces code matching the GWM reference example pattern. |

---

### BMG-023: LIN namespace handler recipe

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Status** | TODO |
| **Summary** | Add LIN namespace support with `LinNamespace`, `publish(WriteSignal)`, and `subscribe_headers()` recipe |
| **Description** | The RL and RLCM reference examples use `LinNamespace` with `publish(WriteSignal(...))` for output and `create_input_handler` with `FrameFilter` for input. LIN slaves also use `subscribe_headers()` for per-frame updates. |
| **Tasks** | 1. Add `LinNamespace` to namespace type enum 2. Implement `LinSlaveRecipe` — LIN input → LIN publish output 3. Implement `LinMasterRecipe` — CAN input → LIN publish + LIN subscribe_headers 4. Write handler templates for LIN patterns 5. Add LIN namespace constructor template (with `interface_name`) 6. Create `examples/rlcm_lin.yaml` example spec |
| **Acceptance** | Generated LIN models match RL/RLCM reference examples. |

---

### BMG-024: `transitions` state machine library integration

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Status** | TODO |
| **Summary** | Add recipe support for complex state machines using the `transitions` Python library |
| **Description** | The full BCM reference example uses `HierarchicalMachine` from the `transitions` library for turn signals (off, left_on/off, right_on/off, hazard_on/off with blinking). This requires a YAML spec that can define states, transitions, triggers, and callbacks — a much richer schema than the simple toggle/blink patterns. |
| **Tasks** | 1. Design YAML schema for state machine definitions (states, transitions, triggers, conditions, callbacks) 2. Add `StateMachineIR` to IR model 3. Implement `StateMachineRecipe` that generates `transitions`-based state machine classes 4. Write templates for state machine class generation 5. Create `examples/bcm_full.yaml` with state machine for turn signals 6. Integrate `create_ticker` callback pattern |
| **Acceptance** | Generated state machine matches the turn_signals.py reference example. Behavioral verification confirms correct state transitions. |

---

### BMG-025: Multi-ECU orchestration spec

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Status** | TODO |
| **Summary** | Allow a single YAML spec to define multiple ECUs with shared namespace topology |
| **Description** | A real vehicle topology has multiple ECUs (BCM, GWM, IHU, SCCM, RLCM, RL) sharing namespaces. Currently each spec defines one ECU. Multi-ECU specs would define the full topology with shared namespace definitions and cross-ECU signal flow. |
| **Tasks** | 1. Design `TopologySpecIR` with multiple `BehavioralModelIR` instances 2. Define shared namespace pool that all ECUs reference 3. Add cross-ECU signal flow validation (signal written by one ECU, read by another) 4. Generate multiple behavioral model packages from single spec 5. Create `examples/full_vehicle.yaml` example |
| **Acceptance** | Single YAML spec generates 6 behavioral models (BCM, GWM, IHU, SCCM, RLCM, RL). Cross-ECU signal flow validated by T3 composition. |

---

### BMG-026: Agent-assisted novel logic proposal

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Status** | TODO |
| **Summary** | When a handler is marked `novel_logic`, an Agent layer can propose a recipe definition |
| **Description** | The `novel_logic` escape hatch currently generates a stub handler (pass). A future Agent layer could analyze the handler's input/output/context and propose a new recipe pattern. The proposed recipe must be reviewed and codified by a human before entering the deterministic registry. |
| **Tasks** | 1. Define Agent prompt template for novel logic analysis 2. Implement `novel_logic_analyzer` that generates recipe proposal JSON 3. Add `bmgen propose` CLI command that runs Agent analysis on novel_logic handlers 4. Add human review workflow (proposed recipe → manual approval → add to registry) 5. Document that Agent-proposed recipes MUST be reviewed before entering CI pipeline |
| **Acceptance** | `bmgen propose examples/custom.yaml` produces a recipe proposal JSON. No Agent-generated code enters the CI pipeline without human review. |

---

### BMG-027: RAG-based pattern discovery

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Status** | TODO |
| **Summary** | Mine existing behavioral model code for new recipe candidates using RAG |
| **Description** | As the corpus of behavioral models grows, RAG can identify common patterns that should be codified as recipes. This is discovery only — proposed recipes still go through the human review and deterministic registry path. |
| **Tasks** | 1. Build code corpus indexer (vector embeddings of behavioral model patterns) 2. Implement pattern similarity search 3. Implement "pattern proposal" output (suggest new recipe based on recurring code patterns) 4. Document that RAG-discovered patterns MUST be codified as recipes before entering compiler pipeline |
| **Acceptance** | RAG system identifies 3+ candidate patterns from the Remotive examples corpus. No RAG-generated code enters CI. |

---

### BMG-028: Claude Code MCP server

| Field | Value |
|-------|-------|
| **Priority** | P3 |
| **Status** | TODO |
| **Summary** | Build a Claude Code MCP server for interactive behavioral model generation |
| **Description** | An MCP server would allow Claude Code to call `bmgen` commands directly from IDE, parse YAML specs, generate code, and verify — all through MCP tool calls. This is a convenience layer, not a core pipeline component. |
| **Tasks** | 1. Define MCP tool schema (bmgen_parse, bmgen_generate, bmgen_verify, bmgen_recipes) 2. Implement MCP server using Anthropic MCP SDK 3. Register in Claude Code MCP config 4. Add IDE workflow documentation |
| **Acceptance** | Claude Code can call `bmgen_generate` MCP tool and receive generated code in conversation context. |

---

### BMG-029: SOME/IP bridge for multi-ECU testing

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Status** | TODO |
| **Summary** | Add SOME/IP protocol bridge for testing multi-ECU behavioral models with simulated service instances |
| **Description** | For integration testing of multi-ECU models, a SOME/IP bridge allows running multiple behavioral models together with simulated service instances (e.g., HVACService, LocationService). |
| **Tasks** | 1. Define SOME/IP service simulation framework 2. Implement mock SOME/IP service instances 3. Create integration test harness for multi-ECU SOME/IP communication 4. Verify cross-ECU event delivery |
| **Acceptance** | Two behavioral models (BCM + GWM) can communicate via simulated SOME/IP events. |

---

### BMG-030: Cuttlefish/Android integration (IHU model)

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Status** | TODO |
| **Summary** | Support IHU-style behavioral models that bridge Remotive broker to Android emulator/Cuttlefish |
| **Description** | The IHU reference example bridges CAN/SOME/IP signals to Android VHAL properties via `BrokerToEmulator` or `BrokerToCuttlefish`. This requires Android SDK integration. |
| **Tasks** | 1. Design `AndroidBridgeRecipe` pattern 2. Add `virtual_device_type` configuration to YAML spec 3. Generate IHU model with bridge selection (emulator/cuttlefish/none) 4. Handle environment variable configuration (ANDROID_EMULATOR_NAME, CUTTLEFISH_GNSS_URL, CUTTLEFISH_VHAL_URL) |
| **Acceptance** | Generated IHU model matches the reference example structure with environment-variable-based bridge selection. |

---

## Ticket Summary

| Priority | Count | Done | TODO |
|----------|-------|------|------|
| P0 | 16 | 16 | 0 |
| P1 | 5 | 3 | 2 |
| P2 | 7 | 0 | 7 |
| P3 | 1 | 0 | 1 |
| **Total** | **29** | **19** | **10** |

### MVP (P0) — COMPLETE ✅

All 16 P0 tickets are done. The MVP is end-to-end functional:
- YAML → IR → Compiler → Generated Python → T1/T2/T3 Verifier → CI
- DirectSignalMapping and ToggleButtonState patterns work
- `bmgen parse/generate/verify/recipes` CLI commands all functional
- 39 tests pass
- Generated code matches Remotive reference examples
