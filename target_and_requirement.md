# goal
I want you to create a detailed architecture and MVP implementation plan for a project named:

`Remotive Behavioral Model Compiler`

# Important context:

The goal is NOT to generate Remotive topology YAML. The goal is to generate Remotive **Behavioral Model Python code** similar to the examples in:
Source code: https://github.com/remotivelabs/remotivelabs-topology-examples
* `remotivelabs-topology-examples/getting_started/models/bcm/__main__.py`
* `remotivelabs-topology-examples/remotive_car/models/bcm/python/bcm/__main__.py`
* `remotivelabs-topology-examples/remotive_car/models/gwm/python/gwm/__main__.py`

# The target architecture is:

`Behavioral Model Spec -> Typed IR -> Deterministic Compiler -> Generated Python Behavioral Model -> 3-layer Verifier -> CI`

The MVP must be a deterministic compiler and verifier. 

Core idea:

* The user writes a small YAML spec describing ECU behavior.
* The system parses the YAML into a typed IR.
* A recipe registry selects known behavior patterns.
* The compiler generates Remotive Behavioral Model Python code.
* The verifier checks generated code structurally, behaviorally, and compositionally.
* CI accepts only generated code that passes verification.


Expected deliverables:

Create a planning document set under:

`docs/architecture/`

with the following files:

1. `MVP_PLAN.md`

   * problem statement
   * goals
   * non-goals
   * MVP scope
   * future scope
   * milestones
   * acceptance criteria

2. `ARCHITECTURE.md`

   * module breakdown
   * package structure
   * responsibilities
   * boundary between recipe registry, IR, compiler, verifier, CLI
   * why this is not GraphRAG
   * why Agent/RAG is future layer only

3. `WORKFLOW.md`

   * developer workflow
   * command flow
   * example CLI usage:

     * `bmgen generate examples/bcm_direct.yaml --out generated/`
     * `bmgen verify generated/`
   * local development workflow
   * CI workflow

4. `DATAFLOW.md`

   * end-to-end dataflow from YAML spec to generated code to verification report
   * include Mermaid diagram
   * include failure paths
   * include `novel_logic` escape hatch

5. `IR_SCHEMA.md`

   * define the typed IR
   * define the YAML input schema
   * define example `bcm_direct.yaml`
   * define example `bcm_toggle.yaml`
   * define required validation rules
   * explain why YAML alone is not enough and why typed IR is needed

6. `VERIFIER_DESIGN.md`

   * describe 3-layer verifier:

     * T1 Structural Verifier
     * T2 Behavioral Verifier
     * T3 Composition Verifier
   * list checks for each layer
   * define verification report JSON schema
   * define PASS/FAIL semantics


IR requirements:

The IR should include at least:

* `BehavioralModelIR`
* `NamespaceIR`
* `HandlerIR`
* `InputSignalIR`
* `OutputSignalIR`
* `StateIR`
* `RecipeIR`
* `PeriodicTaskIR`
* `VerifierRuleIR`

# The IR must support these invariants:

based on given source then define for me approve

Verifier requirements:

T1 Structural Verifier checks:

* generated Python file exists
* Python syntax is valid
* module imports successfully
* handler methods are async
* handler accepts `frame`
* namespace references exist
* output namespace supports restbus
* input handler has matching `FrameFilter`
* can be added, notice me for aprove

T2 Behavioral Verifier checks:

* fake `Frame` with `signals` dictionary can call generated handler
* mocked `restbus.update_signals` receives expected tuples
* can be added, notice me for aprove

T3 Composition Verifier checks:

* no duplicate handler names
* no duplicate state ownership
* no pattern conflicts
* periodic tasks have cleanup
* reset/reboot can reset all owned states
* composed model has no invalid lifecycle behavior
* can be added, notice me for aprove


Verification report JSON should include:

* notice me for aprove


