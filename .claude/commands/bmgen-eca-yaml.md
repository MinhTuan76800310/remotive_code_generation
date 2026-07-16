---
description: Author schema_v2 ECU YAML from natural language; parse-hard-gate with bmgen-eca
argument-hint: "<NL description of ECU behavior> [--out path/to.yaml]"
---

# /bmgen-eca-yaml

User wants schema_v2 ECU YAML from: `$ARGUMENTS`

## Instructions

1. Invoke the same workflow as skill `bmgen-eca-author` (read its `SKILL.md` and references).
2. If `$ARGUMENTS` contains `--out <path>`, write the YAML there; otherwise choose a clear path and state it.
3. After write, run `bmgen-eca parse <path>`.
4. Fix all `E_*` until parse is green. Do not stop early.
5. Report: output path, warning summary, and that generate was **not** run unless user also asked.

Do not use recipe bmgen dialect. Do not invent bus/signal names without asking.
