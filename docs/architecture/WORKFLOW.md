# Workflow — Remotive Behavioral Model Compiler

## Developer Workflow

### Step-by-step: From Spec to Verified Code

```text
1. Write YAML spec          →  examples/bcm_direct.yaml
2. Parse & validate         →  bmgen parse examples/bcm_direct.yaml
3. Generate code            →  bmgen generate examples/bcm_direct.yaml --out generated/
4. Verify generated code    →  bmgen verify generated/
5. If PASS → commit         →  git add generated/ && git commit
6. If FAIL → fix spec       →  Edit YAML spec, re-run from step 2
```

### Step 1: Write YAML Spec

The developer creates a YAML file describing ECU behavior using known recipe patterns:

```yaml
# examples/bcm_direct.yaml
model:
  name: BCM
  ecu_name: BCM

namespaces:
  - name: BCM-BodyCan0
    type: can
    role: output
    restbus:
      sender_filter: BCM
  - name: BCM-DriverCan0
    type: can
    role: input

handlers:
  - name: on_hazard_light
    pattern: DirectSignalMapping
    input:
      namespace: BCM-DriverCan0
      frame_filter: HazardLightButton
      signal: HazardLightButton.HazardLightButton
    output:
      namespace: BCM-BodyCan0
      signals:
        - TurnLightControl.RightTurnLightRequest
        - TurnLightControl.LeftTurnLightRequest
```

### Step 2: Parse & Validate

```bash
bmgen parse examples/bcm_direct.yaml
```

Output (stdout):
```json
{
  "model": { "name": "BCM", "ecu_name": "BCM" },
  "namespaces": [
    { "name": "BCM-BodyCan0", "type": "can", "role": "output", "restbus": { "sender_filter": "BCM" } },
    { "name": "BCM-DriverCan0", "type": "can", "role": "input" }
  ],
  "handlers": [
    { "name": "on_hazard_light", "pattern": "DirectSignalMapping", ... }
  ],
  "validation": { "status": "PASS", "violations": [] }
}
```

If validation fails, the command exits with code 1 and prints violations.

### Step 3: Generate Code

```bash
bmgen generate examples/bcm_direct.yaml --out generated/
```

This produces:
```text
generated/
├── bcm/
│   ├── __init__.py
│   ├── __main__.py        # Complete behavioral model
│   └── log.py             # Logging configuration
```

The `__main__.py` contains the complete Remotive Behavioral Model Python code following the patterns seen in the reference examples.

### Step 4: Verify Generated Code

```bash
bmgen verify generated/
```

This runs T1 → T2 → T3 in sequence and produces a verification report:

```json
{
  "status": "PASS",
  "checks": [
    { "layer": "structural", "name": "file_exists", "status": "PASS", "message": "" },
    { "layer": "structural", "name": "syntax_valid", "status": "PASS", "message": "" },
    { "layer": "structural", "name": "module_imports", "status": "PASS", "message": "" },
    { "layer": "structural", "name": "handler_async", "status": "PASS", "message": "" },
    { "layer": "structural", "name": "handler_accepts_frame", "status": "PASS", "message": "" },
    { "layer": "structural", "name": "namespace_refs_exist", "status": "PASS", "message": "" },
    { "layer": "structural", "name": "output_has_restbus", "status": "PASS", "message": "" },
    { "layer": "structural", "name": "input_has_frame_filter", "status": "PASS", "message": "" },
    { "layer": "behavioral", "name": "handler_callable_with_fake_frame", "status": "PASS", "message": "" },
    { "layer": "behavioral", "name": "direct_signal_mapping_output_correct", "status": "PASS", "message": "" },
    { "layer": "composition", "name": "no_duplicate_handler_names", "status": "PASS", "message": "" },
    { "layer": "composition", "name": "no_duplicate_state_ownership", "status": "PASS", "message": "" },
    { "layer": "composition", "name": "no_pattern_conflicts", "status": "PASS", "message": "" }
  ],
  "generated_files": ["generated/bcm/__main__.py"],
  "errors": []
}
```

### Step 5: Commit or Fix

If `status: PASS`:
```bash
git add generated/
git commit -m "Generate BCM behavioral model from bcm_direct.yaml"
```

If `status: FAIL`:
- Examine the `errors` list in the verification report
- Identify which check failed and why
- Fix the YAML spec (e.g., wrong namespace name, missing restbus config)
- Re-run from step 2

## Command Flow

```text
bmgen parse <yaml>
  │
  ▼ parser.py: read YAML → raw dict
  │
  ▼ builder.py: raw dict → IR dataclasses
  │
  ▼ validators.py: check invariants
  │
  ▼ print validated IR to stdout (or exit 1 on violations)


bmgen generate <yaml> --out <dir>
  │
  ▼ parser + builder + validators (same as parse)
  │
  ▼ registry.py: for each handler, lookup recipe by pattern name
  │
  ▼ recipe.validate(handler_ir): confirm handler IR matches recipe requirements
  │
  ▼ recipe.build_context(handler_ir): produce template context dict
  │
  ▼ context_builder.py: merge all contexts into unified model context
  │
  ▼ python_generator.py: render Jinja2 templates → write files to --out dir


bmgen verify <dir>
  │
  ▼ structural.py: T1 checks (file, syntax, imports, signatures, refs)
  │   ─── if any T1 FAIL → stop, return report with FAIL status
  │
  ▼ behavioral.py: T2 checks (fake frame, mock restbus, expected outputs)
  │   ─── if any T2 FAIL → stop, return report with FAIL status
  │
  ▼ composition.py: T3 checks (duplicates, conflicts, lifecycle)
  │
  ▼ report.py: aggregate all checks → VerificationReport JSON


bmgen recipes
  │
  ▼ registry.py: list all registered recipes
  │
  ▼ print recipe names, descriptions, required IR fields
```

## Example CLI Usage

### DirectSignalMapping (getting_started BCM pattern)

```bash
# Parse the spec
bmgen parse examples/bcm_direct.yaml

# Generate code
bmgen generate examples/bcm_direct.yaml --out generated/

# Verify generated code
bmgen verify generated/

# List available recipes
bmgen recipes
# Output:
# DirectSignalMapping - Read one signal, write same value to outputs
# ToggleButtonState   - Read button, toggle boolean state, write state
# PeriodicBlinkingOutput - Periodic async task with blinking and cleanup
```

### ToggleButtonState (hazard button toggle)

```bash
bmgen generate examples/bcm_toggle.yaml --out generated/
bmgen verify generated/
```

### PeriodicBlinkingOutput (blinking turn signals) — MVP+

```bash
bmgen generate examples/bcm_blinking.yaml --out generated/
bmgen verify generated/
```

## Local Development Workflow

```bash
# Clone and setup
git clone <repo>
cd remotive-bm-compiler
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Generate and verify locally
bmgen generate examples/bcm_direct.yaml --out _local_gen/
bmgen verify _local_gen/

# Clean generated files
rm -rf _local_gen/
```

## CI Workflow

```yaml
# .github/workflows/verify.yml
name: Verify Generated Behavioral Models

on:
  push:
    paths:
      - 'examples/*.yaml'
      - 'bmgen/**'
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install bmgen
        run: pip install -e ".[dev]"

      - name: Generate all example models
        run: |
          for yaml in examples/*.yaml; do
            bmgen generate "$yaml" --out generated/
          done

      - name: Verify all generated models
        run: |
          for yaml in examples/*.yaml; do
            bmgen verify generated/ || exit 1
          done

      - name: Run test suite
        run: pytest tests/ -v
```

### CI Failure Behavior

If any verification check fails:
1. CI job exits with code 1
2. The verification report JSON is printed in CI logs
3. The PR cannot be merged until the spec or code is fixed
4. No generated code that fails verification enters the main branch

### CI Success Behavior

If all verification checks pass:
1. CI job exits with code 0
2. Generated code is considered verified and can be committed
3. The PR can be merged
