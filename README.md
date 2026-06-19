# 🔧 Remotive Behavioral Model Compiler

> **A deterministic compiler that transforms YAML behavior specs into verified Remotive Behavioral Model Python code.**

[![CI: Verify Generated Models](https://img.shields.io/badge/CI-Verify_Generated_Models-blue?logo=github-actions)](.github/workflows/verify.yml)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](remotive-bm-compiler/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Version](https://img.shields.io/badge/Version-0.1.0-orange)](remotive-bm-compiler/pyproject.toml)

---

## 📖 Table of Contents

- [Why This Project Exists](#-why-this-project-exists)
- [The Solution](#-the-solution)
- [Architecture](#-architecture)
- [Available Recipes](#-available-recipes)
- [How to Use](#-how-to-use)
- [Verification System](#-verification-system)
- [Real-World Example: Child Presence Detection](#-real-world-example-child-presence-detection)
- [Future Vision](#-future-vision)

---

## 🎯 Why This Project Exists

### The Problem

Modern vehicles contain **6–50+ ECUs** (Electronic Control Units) that communicate via CAN bus. Simulating these ECUs for development, testing, and validation requires writing **Behavioral Model Python code** — async handlers that read CAN signals, apply logic, and write output signals via the Remotive Labs broker.

The current workflow is **manual, error-prone, and non-repeatable**:

```mermaid
flowchart TD
    A["📖 Engineer reads ECU spec<br/><i>(PDF, BPMN, requirements)</i>"] --> B["⌨️ Hand-writes Python behavioral model"]
    B --> C["🪲 Subtle bugs appear:<br/>wrong signal names, missing async,<br/>missing restbus config..."]
    C --> D["⏱️ Debugs, fixes, re-tests<br/><b>2–4 hours per ECU</b>"]
    D --> E["⚠️ 6 ECUs × 2-4 hrs = <b>12–24 hours</b> of manual work"]

    F["❌ No guarantee next ECU follows the same pattern"] -.-> E
    G["❌ No automated verification that code matches spec"] -.-> E
    H["❌ Same spec → different code (non-deterministic)"] -.-> E

    style E fill:#f66,stroke:#c00,color:#fff
    style F fill:#fbb,stroke:#c00
    style G fill:#fbb,stroke:#c00
    style H fill:#fbb,stroke:#c00
```

**Three core pain points:**

| Pain Point | Description | Impact |
|---|---|---|
| 🔁 **Repetitive patterns** | 80%+ of ECU handlers follow 5-6 known patterns (direct forward, toggle, blink, threshold, logic gates) | Engineers rewrite the same code structure over and over |
| 🪲 **Silent bugs** | Missing `async`, wrong namespace refs, missing `restbus` config, incorrect `FrameFilter` — these pass syntax check but fail at runtime | Hours of debugging per ECU |
| 🎲 **Non-deterministic** | Same spec → different code depending on who writes it, when, and how | No reproducibility, no CI guarantee |

### Why Not Just Use LLM/AI Code Generation?

LLM-generated code is **non-deterministic** — the same prompt can produce different code each time. This is unacceptable for safety-critical automotive software where:

- The code must be **verifiable** (every line must pass structural + behavioral + composition checks)
- The code must be **reproducible** (same spec → same code, always)
- The code must be **traceable** (every output signal maps to a known recipe pattern)

Agent/RAG layers are planned as a **future augmentation** (helping write specs and discover new patterns), but the core compilation pipeline must remain **deterministic and LLM-free**.

---

## 💡 The Solution

### The `bmgen` Compiler Pipeline

```mermaid
flowchart TD
    A["📝 Engineer writes YAML spec<br/><i>10–30 lines</i>"] --> B["🔍 bmgen parses YAML → typed IR"]
    B --> C["✅ Validates invariants"]
    C --> D["📋 Recipe registry selects pattern"]
    D --> E["⚙️ Compiler generates Python<br/>from Jinja2 templates"]
    E --> F["🧪 3-Layer Verifier checks<br/>structural + behavioral + composition"]
    F --> G{"Result?"}
    G -->|"PASS"| H["✅ Commit to CI"]
    G -->|"FAIL"| I["🔄 Fix spec, re-run"]

    J["⏱️ 6 ECUs × 30 sec = <b>3 minutes total</b>"] -.-> H
    K["✅ Every generated line passes T1/T2/T3"] -.-> H
    L["✅ Same YAML → same code, <b>always</b>"] -.-> H

    style H fill:#4c4,stroke:#090,color:#fff
    style I fill:#f66,stroke:#c00,color:#fff
    style J fill:#eee,stroke:#999
    style K fill:#eee,stroke:#999
    style L fill:#eee,stroke:#999
```

### The Core Invariant

> **No line of generated Python code in the CI path comes from an LLM.**
> All code comes from templates + recipe logic. Agent assistance may help *write recipes* or *write YAML specs*, but the compiler path remains deterministic.

---

## 🏗️ Architecture

### End-to-End Pipeline

```mermaid
flowchart TD
    A["📝 YAML Spec File<br/><i>examples/bcm_direct.yaml</i>"] --> B["🔍 parser.py<br/>YAML → raw dict"]
    B --> C["🏗️ builder.py<br/>raw dict → IR dataclasses"]
    C --> D{"⚖️ validators.py<br/>Invariant checks"}
    D -->|"VIOLATIONS"| E["❌ EXIT 1<br/>Print violations"]
    D -->|"ALL PASS"| F["📋 registry.py<br/>Pattern lookup per handler"]
    F --> G{"🧪 recipe.validate<br/>handler_ir"}
    G -->|"INVALID"| H["❌ EXIT 1<br/>Recipe mismatch"]
    G -->|"VALID"| I["🧩 recipe.build_context<br/>handler_ir → context dict"]
    I --> J["🔗 context_builder.py<br/>Merge all contexts"]
    J --> K["⚙️ python_generator.py<br/>Jinja2 template rendering"]
    K --> L["📄 Generated Python Files<br/>__main__.py, __init__.py, log.py"]
    L --> M["T1: Structural<br/>✓ file exists ✓ syntax ✓ imports"]
    M -->|"T1 FAIL"| N["❌ Report: FAIL"]
    M -->|"T1 PASS"| O["T2: Behavioral<br/>✓ fake Frame ✓ mock restbus"]
    O -->|"T2 FAIL"| N
    O -->|"T2 PASS"| P["T3: Composition<br/>✓ no conflicts ✓ lifecycle"]
    P -->|"T3 FAIL"| N
    P -->|"T3 PASS"| Q["✅ Report: PASS<br/>All checks verified"]

    style E fill:#f44,stroke:#900,color:#fff
    style H fill:#f44,stroke:#900,color:#fff
    style N fill:#f44,stroke:#900,color:#fff
    style Q fill:#4f4,stroke:#090,color:#fff
    style A fill:#69f,stroke:#369,color:#fff
    style L fill:#ff9,stroke:#990
```

### Module Boundaries

```mermaid
flowchart TB
    subgraph IR["ir/ — Pure Data Layer"]
        IR1["parser.py — YAML → raw dict"]
        IR2["model.py — IR dataclass definitions"]
        IR3["builder.py — raw dict → validated IR"]
        IR4["validators.py — invariant checks"]
    end

    subgraph Recipes["recipes/ — Validation + Context Layer"]
        R1["registry.py — pattern name → Recipe lookup"]
        R2["base.py — abstract Recipe class"]
        R3["direct_signal_mapping.py"]
        R4["toggle_button_state.py"]
        R5["periodic_blinking_output.py"]
        R6["logic_gate.py"]
        R7["threshold_mapping.py"]
    end

    subgraph Compiler["compiler/ — Generation Layer"]
        C1["context_builder.py — IR + recipes → template context"]
        C2["python_generator.py — Jinja2 → Python files"]
        C3["templates/*.j2 — handler templates"]
    end

    subgraph Verifier["verifier/ — Checking Layer"]
        V1["structural.py — T1"]
        V2["behavioral.py — T2"]
        V3["composition.py — T3"]
        V4["runner.py — orchestrates T1→T2→T3"]
        V5["report.py — VerificationReport JSON"]
    end

    CLI["cli.py — Orchestrator<br/><i>no business logic</i>"]

    YAML["📝 YAML Spec"] --> IR
    IR -->|"validated BehavioralModelIR"| Recipes
    Recipes -->|"RecipeContext dicts"| Compiler
    Compiler -->|"generated Python files"| Verifier
    IR -.->|"IR for expected behavior"| Verifier
    CLI --> IR & Recipes & Compiler & Verifier

    IR -.-x Compiler & Verifier & Recipes
    Recipes -.-x Compiler & Verifier
    Compiler -.-x Verifier

    style IR fill:#69f,stroke:#369,color:#fff
    style Recipes fill:#9f9,stroke:#090,color:#fff
    style Compiler fill:#ff9,stroke:#990,color:#333
    style Verifier fill:#f9f,stroke:#909,color:#333
    style CLI fill:#eee,stroke:#999
    style YAML fill:#69f,stroke:#369,color:#fff
```

**Boundary rules:**

| Layer | Reads From | Writes To | Never Imports |
|---|---|---|---|
| `ir/` | YAML only | BehavioralModelIR dataclasses | compiler, recipes, verifier |
| `recipes/` | IR dataclasses | Context dicts (plain Python dicts) | compiler, verifier, filesystem |
| `compiler/` | IR + recipe contexts | Filesystem (Python files) | verifier |
| `verifier/` | Filesystem + IR | VerificationReport JSON | compiler, recipes (never generates code) |

### IR Data Flow (YAML → Dataclasses → Templates → Code)

```mermaid
flowchart LR
    subgraph "YAML Input"
        Y1["model: BCM<br/>ecu_name: BCM"]
        Y2["namespaces:<br/>BCM-BodyCan0 (output)<br/>BCM-DriverCan0 (input)"]
        Y3["handlers:<br/>on_hazard_light<br/>pattern: DirectSignalMapping"]
    end

    subgraph "Typed IR Dataclasses"
        IR1["BehavioralModelIR<br/>name='BCM'<br/>ecu_name='BCM'"]
        IR2["NamespaceIR<br/>name='BCM-BodyCan0'<br/>python_var='body_can_0'"]
        IR3["HandlerIR<br/>name='on_hazard_light'<br/>pattern='DirectSignalMapping'<br/>input_signals=[...]<br/>output_signals=[...]"]
    end

    subgraph "Recipe Context"
        RC1["RecipeContext<br/>handler_name='on_hazard_light'<br/>input_signal_var='hazard_signal'<br/>output_tuples=[(sig, expr)]"]
    end

    subgraph "Generated Python"
        GP1["class BCM:<br/>body_can_0: CanNamespace<br/>async def on_hazard_light(self, frame)"]
    end

    Y1 & Y2 & Y3 --> IR1 & IR2 & IR3
    IR3 --> RC1
    RC1 --> GP1

    style Y1 fill:#69f,stroke:#369,color:#fff
    style Y2 fill:#69f,stroke:#369,color:#fff
    style Y3 fill:#69f,stroke:#369,color:#fff
    style IR1 fill:#ff9,stroke:#990
    style IR2 fill:#ff9,stroke:#990
    style IR3 fill:#ff9,stroke:#990
    style RC1 fill:#9f9,stroke:#090
    style GP1 fill:#f9f,stroke:#909
```

### Why Typed IR (Not Just YAML)?

| YAML (Serialization) | Typed IR (Compilation) |
|---|---|
| No type enforcement — `"BCM"` could be anything | Every field has a Python type — errors caught at build time |
| No invariant validation — duplicate names are fine | Validators enforce uniqueness, cross-refs, restbus configs |
| No behavioral semantics — a string `"DirectSignalMapping"` is just a string | Maps to a Recipe class that validates handler structure |
| No deterministic compilation — ambiguous specs | Validated IR → deterministic template rendering |

---

## 🍳 Available Recipes

Recipes are **known behavioral patterns** — the building blocks of ECU logic.

| Recipe | Pattern | Inputs | Outputs | State | Description | Real-World Example |
|---|---|---|---|---|---|---|
| **DirectSignalMapping** | `DirectSignalMapping` | 1 | ≥1 | ❌ | Read one signal → forward same value to outputs | Hazard light button → turn light request |
| **ToggleButtonState** | `ToggleButtonState` | 1 | ≥1 | ✅ (bool) | Read button → toggle boolean → write 1/0 to outputs | Hazard button press ON, press again OFF |
| **PeriodicBlinkingOutput** | `PeriodicBlinkingOutput` | 1 | ≥1 | ✅ (bool) | State enables blinking → periodic async ticker → cleanup | Turn signal blinking at 1s interval |
| **ThresholdMapping** | `ThresholdMapping` | 1 | ≥1 | ❌ | Compare analog input against threshold → output 1/0 | Seat weight > 5kg → child detected |
| **LogicAnd** | `LogicAnd` | ≥2 | ≥1 | ❌ | AND of N input signals → 0/1 result | Door locked AND seatbelt ON → safe |
| **LogicOr** | `LogicOr` | ≥2 | ≥1 | ❌ | OR of N input signals → 0/1 result | Any door open → warning |
| **LogicXor** | `LogicXor` | ≥2 | ≥1 | ❌ | XOR of N inputs (odd true) → 0/1 result | Exclusive mode selection |
| **LogicNot** | `LogicNot` | 1 | ≥1 | ❌ | NOT (invert) single input → 0/1 result | Invert enable → disable |

### Recipe Visual Pattern Map

```mermaid
flowchart TB
    subgraph Stateless["Stateless Recipes"]
        DSM["<b>DirectSignalMapping</b><br/>Input=1 ──► Out1, Out2<br/><i>same value forwarded</i>"]
        TM["<b>ThresholdMapping</b><br/>Input=7 ──► 1 if > 5.0 else 0<br/><i>analog → boolean</i>"]
        LG["<b>Logic Gates</b><br/>A, B ──► AND/OR/XOR ──► 0/1<br/><i>boolean combinations</i>"]
    end

    subgraph Stateful["Stateful Recipes"]
        TBS["<b>ToggleButtonState</b><br/>Press=1 ──► Toggle(bool) ──► 1/0<br/><i>press ON, press again OFF</i>"]
        PBO["<b>PeriodicBlinkingOutput</b><br/>Enable=1 ──► blink_enabled ──► ◐◑◐◑<br/><i>ticker at 1s interval</i>"]
    end

    style Stateless fill:#ddf,stroke:#369,color:#333
    style Stateful fill:#fdd,stroke:#c00,color:#333
    style DSM fill:#69f,stroke:#369,color:#fff
    style TM fill:#69f,stroke:#369,color:#fff
    style LG fill:#69f,stroke:#369,color:#fff
    style TBS fill:#f9f,stroke:#909,color:#333
    style PBO fill:#f9f,stroke:#909,color:#333
```

---

## 🚀 How to Use

### Installation

```bash
# Clone and install
cd remotive-bm-compiler
pip install -e ".[dev]"
```

### Step 1: Write a YAML Spec

Create a small YAML file describing ECU behavior:

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

Output:
```text
Model: BCM (ECU: BCM)
Namespaces: 2
  - BCM-BodyCan0 (can, role=output, var=body_can_0) (restbus: sender_filter=BCM)
  - BCM-DriverCan0 (can, role=input, var=driver_can_0)
Handlers: 1
  - on_hazard_light (pattern=DirectSignalMapping, novel_logic=False)
    Input: BCM-DriverCan0 / HazardLightButton / HazardLightButton.HazardLightButton
    Output: BCM-BodyCan0 / ['TurnLightControl.RightTurnLightRequest', 'TurnLightControl.LeftTurnLightRequest']
Validation: PASS
```

### Step 3: Generate Code

```bash
bmgen generate examples/bcm_direct.yaml --out generated/
```

Output:
```text
Generated 3 files in generated/:
  - bcm/__main__.py
  - bcm/__init__.py
  - bcm/log.py
```

### Step 4: Verify Generated Code

```bash
bmgen verify generated/ --spec examples/bcm_direct.yaml
```

Output:
```text
Verification result: PASS
Checks: 13
  ✓ [structural] file_exists: PASS
  ✓ [structural] syntax_valid: PASS
  ✓ [structural] module_imports: PASS
  ✓ [structural] handler_async: PASS
  ✓ [structural] handler_accepts_frame: PASS
  ✓ [structural] namespace_refs_exist: PASS
  ✓ [structural] output_has_restbus: PASS
  ✓ [structural] input_has_frame_filter: PASS
  ✓ [behavioral] handler_callable_with_fake_frame: PASS
  ✓ [behavioral] direct_signal_mapping_output_correct: PASS
  ✓ [composition] no_duplicate_handler_names: PASS
  ✓ [composition] no_duplicate_state_ownership: PASS
  ✓ [composition] no_pattern_conflicts: PASS
```

### CLI Command Summary

```mermaid
flowchart LR
    P["<b>bmgen parse</b><br/><i>yaml_file</i>"] -->|"YAML → IR → validate"| S1["stdout"]
    G["<b>bmgen generate</b><br/><i>yaml_file --out dir</i>"] -->|"YAML → IR → recipes → code"| S2["Python files"]
    V["<b>bmgen verify</b><br/><i>dir --spec yaml</i>"] -->|"T1→T2→T3"| S3["Report JSON"]
    R["<b>bmgen recipes</b>"] -->|"List patterns"| S4["stdout"]

    style P fill:#69f,stroke:#369,color:#fff
    style G fill:#9f9,stroke:#090,color:#fff
    style V fill:#ff9,stroke:#990,color:#333
    style R fill:#f9f,stroke:#909,color:#333
```

### What Gets Generated

Each YAML spec generates a complete behavioral model Python package:

```
generated/
└── bcm/
    ├── __main__.py    ← Complete behavioral model (imports, class, handlers, main(), entry point)
    ├── __init__.py    ← Package marker
    └── log.py         ← structlog configuration
```

The `__main__.py` follows the Remotive Labs behavioral model conventions:

```python
import asyncio
import logging
from dataclasses import dataclass

from remotivelabs.broker import BrokerClient, Frame
from remotivelabs.topology.behavioral_model import BehavioralModel
from remotivelabs.topology.cli.behavioral_model import BehavioralModelArgs
from remotivelabs.topology.namespaces import filters
from remotivelabs.topology.namespaces.can import CanNamespace, RestbusConfig


@dataclass
class BCM:
    body_can_0: CanNamespace

    async def on_hazard_light(self, frame: Frame) -> None:
        hazard_signal = frame.signals["HazardLightButton.HazardLightButton"]
        await self.body_can_0.restbus.update_signals(
            ("TurnLightControl.RightTurnLightRequest", hazard_signal),
            ("TurnLightControl.LeftTurnLightRequest", hazard_signal),
        )


async def main(avp: BehavioralModelArgs):
    async with BrokerClient(url=avp.url, auth=avp.auth) as broker_client:
        body_can_0 = CanNamespace(
            "BCM-BodyCan0", broker_client,
            restbus_configs=[RestbusConfig(
                [filters.SenderFilter(ecu_name="BCM")],
                delay_multiplier=avp.delay_multiplier)],
        )
        driver_can_0 = CanNamespace("BCM-DriverCan0", broker_client)
        bcm = BCM(body_can_0)
        async with BehavioralModel(
            "BCM", namespaces=[body_can_0, driver_can_0],
            broker_client=broker_client,
            input_handlers=[
                driver_can_0.create_input_handler(
                    [filters.FrameFilter("HazardLightButton")],
                    bcm.on_hazard_light,
                )
            ],
        ) as bm:
            await bm.run_forever()

if __name__ == "__main__":
    args = BehavioralModelArgs.parse()
    asyncio.run(main(args))
```

### Novel Logic Escape Hatch

When a behavior pattern isn't in the registry, mark it as `novel_logic`:

```yaml
handlers:
  - name: on_custom_logic
    pattern: CustomBehavior
    novel_logic: true
    input:
      namespace: BCM-DriverCan0
      frame_filter: CustomFrame
      signal: CustomSignal.Value
    output:
      namespace: BCM-BodyCan0
      signals:
        - CustomOutput.Signal
```

This generates a stub:
```python
async def on_custom_logic(self, frame: Frame) -> None:
    # novel_logic: implement manually
    # pattern: CustomBehavior
    # input: CustomSignal.Value from BCM-DriverCan0
    # output: CustomOutput.Signal to BCM-BodyCan0
    pass
```

Verification: T1 PASS (stub exists), T2 SKIP (novel_logic), T3 PASS (no conflicts). The report includes a warning that manual implementation is required.

---

## 🔍 Verification System

### 3-Layer Verification Architecture

```mermaid
flowchart TD
    CODE["📄 Generated Python Code"]

    subgraph T1["T1: Structural Verifier"]
        T1a["✓ File exists"]
        T1b["✓ Python syntax valid"]
        T1c["✓ Module imports succeed"]
        T1d["✓ Handlers are async def"]
        T1e["✓ Handlers accept frame: Frame"]
        T1f["✓ Namespace refs exist"]
        T1g["✓ Output has restbus config"]
        T1h["✓ Input has FrameFilter"]
        T1i["✓ restbus.update_signals used"]
        T1j["✓ main() function exists"]
        T1k["✓ __main__ entry point exists"]
    end

    subgraph T2["T2: Behavioral Verifier"]
        T2a["✓ Handler callable with fake Frame"]
        T2b["✓ Mock restbus receives calls"]
        T2c["✓ DirectMapping: output = input"]
        T2d["✓ Toggle: press once → ON"]
        T2e["✓ Toggle: press twice → OFF"]
        T2f["✓ Toggle: press zero → no change"]
    end

    subgraph T3["T3: Composition Verifier"]
        T3a["✓ No duplicate handler names"]
        T3b["✓ No duplicate state ownership"]
        T3c["✓ No pattern conflicts"]
        T3d["✓ Periodic tasks have cleanup"]
        T3e["✓ Reset covers all owned states"]
        T3f["✓ Reset covers all output namespaces"]
        T3g["✓ Input ≠ Output namespace"]
        T3h["✓ FrameFilter unique per namespace"]
        T3i["✓ Novel logic handlers listed"]
        T3j["✓ Lifecycle valid"]
    end

    CODE --> T1
    T1 -->|"T1 PASS"| T2
    T2 -->|"T2 PASS"| T3
    T3 -->|"T3 PASS"| PASS["✅ PASS — Verified"]
    T1 -->|"T1 FAIL"| FAIL1["❌ FAIL — T2/T3 skipped"]
    T2 -->|"T2 FAIL"| FAIL2["❌ FAIL — T3 skipped"]
    T3 -->|"T3 FAIL"| FAIL3["❌ FAIL"]

    style CODE fill:#ff9,stroke:#990,color:#333
    style T1 fill:#ddf,stroke:#369
    style T2 fill:#dfd,stroke:#090
    style T3 fill:#fdd,stroke:#c00
    style PASS fill:#4c4,stroke:#090,color:#fff
    style FAIL1 fill:#f44,stroke:#900,color:#fff
    style FAIL2 fill:#f44,stroke:#900,color:#fff
    style FAIL3 fill:#f44,stroke:#900,color:#fff
```

### Fail-Fast Design

The verifier runs layers in strict sequence: **T1 → T2 → T3**. If T1 fails, T2 and T3 are skipped entirely. This prevents wasting time on behavioral checks when the code is structurally broken.

```mermaid
flowchart LR
    T1["T1: Structural"] --> R1{"Result?"}
    R1 -->|"FAIL"| STOP1["❌ Stop — T2/T3 skipped"]
    R1 -->|"PASS"| T2["T2: Behavioral"]
    T2 --> R2{"Result?"}
    R2 -->|"FAIL"| STOP2["❌ Stop — T3 skipped"]
    R2 -->|"PASS"| T3["T3: Composition"]
    T3 --> R3{"Result?"}
    R3 -->|"FAIL"| STOP3["❌ Stop"]
    R3 -->|"PASS"| OK["✅ Verified — CI can merge"]

    NL["⚠️ novel_logic handlers:<br/>T2 SKIP, T3 PASS (warning)"] -.-> OK

    style STOP1 fill:#f44,stroke:#900,color:#fff
    style STOP2 fill:#f44,stroke:#900,color:#fff
    style STOP3 fill:#f44,stroke:#900,color:#fff
    style OK fill:#4c4,stroke:#090,color:#fff
    style NL fill:#eee,stroke:#999
```

### Verification Report

Every verification produces a JSON report:

```json
{
  "status": "PASS",
  "checks": [
    {"layer": "structural", "name": "file_exists", "status": "PASS"},
    {"layer": "structural", "name": "syntax_valid", "status": "PASS"},
    {"layer": "behavioral", "name": "handler_callable_with_fake_frame", "status": "PASS"},
    {"layer": "composition", "name": "no_duplicate_handler_names", "status": "PASS"}
  ],
  "generated_files": ["generated/bcm/__main__.py"],
  "errors": [],
  "warnings": []
}
```

---

## 🚗 Real-World Example: Child Presence Detection

This project has already been applied to a real automotive use case: **Child Presence Detection (CPD)** across 6 ECUs. Each ECU's behavior was specified in a YAML file and compiled into verified Python behavioral models.

### ECU Architecture for CPD

```mermaid
flowchart TB
    CAM["📷 CAM-ECU<br/><i>Camera Image Acquisition</i><br/>Recipe: DirectSignalMapping"]
    ZON["🧠 Zonal ECU<br/><i>Central Logic Coordinator</i><br/>Recipe: LogicOr + DirectSignalMapping"]
    AIR["💥 Airbag ECU<br/><i>Final Restraint Control</i><br/>Recipe: DirectSignalMapping"]
    SEAT["🪑 SubECU Seat<br/><i>Weight Threshold Detection</i><br/>Recipe: ThresholdMapping"]
    COCK["💻 Cockpit ECU<br/><i>Warning & HMI Display</i><br/>Recipe: DirectSignalMapping + ToggleButtonState"]
    CC["🖥️ Central Computer<br/><i>Decision & HMI Control</i><br/>Recipe: LogicAnd + LogicOr"]

    CAM -->|"normalized image"| ZON
    SEAT -->|"weight > threshold → detected"| ZON
    ZON -->|"child present decision"| AIR
    ZON -->|"child present decision"| COCK
    ZON -->|"child present decision"| CC
    COCK -->|"warning status"| CC

    style CAM fill:#69f,stroke:#369,color:#fff
    style ZON fill:#f9f,stroke:#909,color:#333
    style AIR fill:#f66,stroke:#c00,color:#fff
    style SEAT fill:#9f9,stroke:#090,color:#fff
    style COCK fill:#ff9,stroke:#990,color:#333
    style CC fill:#ddf,stroke:#369,color:#333
```

### Generated Models

The 6 ECU specs in `examples/cpd/` compile into 6 verified behavioral models in `_generated/`:

```bash
# Generate all 6 CPD models
for yaml in examples/cpd/*.yaml; do
  slug=$(basename "$yaml" .yaml)
  bmgen generate "$yaml" --out "_generated/$slug"
  bmgen verify "_generated/$slug" --spec "$yaml"
done
```

```
_generated/
├── airbag_ecu/     ← DirectSignalMapping (airbag control forwarding)
├── cam_ecu/        ← DirectSignalMapping (camera image forwarding)
├── central_computer/ ← LogicAnd + LogicOr (decision logic)
├── cockpit_ecu/    ← DirectSignalMapping + ToggleButtonState (warning)
├── subecu_seat/    ← ThresholdMapping (weight → child detected)
├── zonal_ecu/      ← LogicOr + DirectSignalMapping (central coordinator)
```

---

## 🔮 Future Vision

### Phase Roadmap

```mermaid
flowchart LR
    P1["✅ Phase 1<br/><b>MVP</b><br/>Deterministic Compiler<br/>+ 3-Layer Verifier<br/>8 recipes<br/>6 CPD ECU models"]
    P2["🔜 Phase 2<br/><b>Recipe Expansion</b><br/>SOME/IP, LIN bus<br/>State machines, Debounce<br/>Analog mapping<br/>Priority override"]
    P3["🔮 Phase 3<br/><b>Agent/RAG</b><br/>Pattern discovery<br/>Spec writing assist<br/>Novel logic proposals<br/>MCP integration"]
    P4["🌟 Phase 4<br/><b>Full Platform</b><br/>Topology generation<br/>End-to-end CI<br/>Fleet simulation<br/>ISO 26262 safety case"]

    P1 --> P2 --> P3 --> P4

    style P1 fill:#4c4,stroke:#090,color:#fff
    style P2 fill:#ff9,stroke:#990,color:#333
    style P3 fill:#69f,stroke:#369,color:#fff
    style P4 fill:#f9f,stroke:#909,color:#333
```

### Phase Details

**Phase 1 — Current MVP ✅**
- YAML → Typed IR → Recipe Registry → Jinja2 Templates
- 8 recipes: Direct, Toggle, Blink, Threshold, LogicAnd/Or/Xor/Not
- T1/T2/T3 verification with fail-fast pipeline
- CI integration: `bmgen verify` blocks merges on FAIL
- Real-world proof: 6 CPD ECU models verified

**Phase 2 — Recipe Expansion 🔜**
- Multi-frame handlers (SOME/IP service calls)
- LIN bus recipe patterns
- Sequence recipes (multi-step state machines)
- Debounce recipe (noise filtering on inputs)
- Analog mapping (linear interpolation tables)
- Priority override recipes (hazard overrides turn signal)
- Target: Cover 95%+ of production ECU patterns

**Phase 3 — Agent-Assisted Augmentation 🔮**

```mermaid
flowchart TB
    subgraph Core["Deterministic Core (Phase 1-2)"]
        CORE["YAML → IR → Recipes → Templates → Code → Verify"]
    end

    subgraph Agent["Agent/RAG Layer (Augmentation ONLY)"]
        A1["🔍 Pattern discovery<br/>Mine behavioral models for new recipe candidates"]
        A2["📝 Spec writing assist<br/>Help engineers write YAML from requirements docs"]
        A3["💡 Novel logic proposals<br/>Agent proposes → human reviews → codifies recipe"]
        A4["🔌 MCP integration<br/>Claude Code server, VS Code extension, Dashboard"]
    end

    Agent -.->|"Helps write specs & recipes"| Core
    Core -.-x|"Agent NEVER replaces"| Core

    INV["<b>INVARIANT:</b><br/>No LLM output enters CI pipeline directly<br/>Same YAML → Same Code → Always"]

    style Core fill:#4c4,stroke:#090,color:#fff
    style Agent fill:#69f,stroke:#369,color:#fff
    style INV fill:#f66,stroke:#c00,color:#fff
```

**Phase 4 — Full Automotive Simulation Platform 🌟**
- Auto-generate topology YAML from behavioral model specs
- End-to-end CI: spec → code → topology → test → deploy
- Fleet simulation: run 6+ ECUs simultaneously
- CAN signal database integration (.arxml/.dbc parsing)
- OTA update simulation: behavioral model hot-swap
- Safety case generation: verification report → ISO 26262

### Key Design Principle Across All Phases

> **The deterministic compiler + verifier is the foundation.**
> Agent/RAG/MCP layers wrap around it, augment it, and help humans use it more effectively — but they never replace the deterministic core pipeline. The invariant holds across all future phases:

> **Same YAML → Same Code → Same Verification → Same CI Decision. Always.**

---

## 📚 Documentation

| Document | Description |
|---|---|
| [MVP_PLAN.md](docs/architecture/MVP_PLAN.md) | Problem statement, goals, scope, milestones |
| [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | Module breakdown, boundaries, design rationale |
| [WORKFLOW.md](docs/architecture/WORKFLOW.md) | Developer workflow, CLI usage, CI |
| [DATAFLOW.md](docs/architecture/DATAFLOW.md) | End-to-end dataflow with Mermaid diagrams |
| [IR_SCHEMA.md](docs/architecture/IR_SCHEMA.md) | Typed IR, YAML schema, validation rules |
| [VERIFIER_DESIGN.md](docs/architecture/VERIFIER_DESIGN.md) | 3-layer verifier design |

---

## 🧪 Running Tests

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run full test suite
pytest tests/ -v

# Run specific test categories
pytest tests/test_ir_validation.py -v       # IR invariant tests
pytest tests/test_compile_direct_mapping.py -v  # DirectSignalMapping generation
pytest tests/test_verify_generated.py -v     # Verification pipeline tests
```

---

## 📜 License

MIT
