# Acceptance checklist — bmgen-eca-author

## Scripted (Task 5)

- [x] T1: Skill file exists; description mentions schema_v2 / bmgen-eca / E_*
- [x] T2: `bmgen-eca parse` green on references/examples/door_ecu.min.yaml
- [x] T3: Hook exit 2 on deliberate bad YAML with E_* in stderr
- [x] T4: Hook exit 0 on remotive-bm-compiler/examples/bcm_direct.yaml (skip)
- [x] T5: references include 03 graph, 02 five subdomains, 05 domains, 06 map, 07 errors
- [x] T6: no marketplace plugin package; all under .claude/
- [x] S5: SKILL.md says generate is optional / not required for DONE

Scripted block result: **ACCEPTANCE_SCRIPTED_OK** (verified 2026-07-16)

## Manual NL smoke (human)

Left for interactive Claude Code session. Prompt:

> Viết ECU YAML schema_v2 cho cửa trượt: nhận TargetPosition, clamp min/max, mỗi 0.2s bước current_pos, publish CurrentPosition + IsMoving. Bus/signal dùng đúng fixture DoorECU.

Expect:
1. Skill engages (or user runs `/bmgen-eca-yaml …`)
2. YAML written
3. `bmgen-eca parse` green (hook and/or skill)
4. No claim of DONE while red

- [ ] S1 manual: NL smoke passes in interactive session
