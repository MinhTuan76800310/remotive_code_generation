# Acceptance checklist — bmgen-eca-author

## Scripted

- [x] T1: Skill file exists; description mentions schema_v2 / bmgen-eca / E_*
- [x] T2: `bmgen-eca parse` green on references/examples/door_ecu.min.yaml
- [x] T3: Hook exit 2 on deliberate bad YAML with E_* in stderr
- [x] T4: Hook exit 0 on remotive-bm-compiler/examples/bcm_direct.yaml (skip)
- [x] T5: references include 03 graph, 02 five subdomains, 05 domains, 06 map, 07 errors
- [x] T6: no marketplace plugin package; all under .claude/
- [x] S5: SKILL.md says generate is optional / not required for DONE
- [ ] T7: pulse IsDone pattern taught in skill — `references/08-pulse-done.md` exists; `examples/seat_ecu.min.yaml` exists; `02-subdomains.md` has service-order section; `03-field-graph.md` has edge-memory + pulse sub-graphs; `07-errors-fix.md` has non-dialect table

Scripted block result: **ACCEPTANCE_SCRIPTED_OK** (verified 2026-07-16)

### T7 scripted verification (pulse contract)

```bash
# 1) Both golden examples parse green with the new dialect features
bmgen-eca parse .claude/skills/bmgen-eca-author/references/examples/door_ecu.min.yaml
bmgen-eca parse .claude/skills/bmgen-eca-author/references/examples/seat_ecu.min.yaml
# expect: exit 0 each, "ok: 0 warnings"

# 2) Generated BM is byte-identical to live models/door_ecu/__main__.py
bmgen-eca generate .claude/skills/bmgen-eca-author/references/examples/door_ecu.min.yaml \
  --out /tmp/skill_check
md5sum /tmp/skill_check/bmgen_generated/door_ecu/__main__.py \
       test_env/remotivelabs-topology-examples/passenger_welcome/models/door_ecu/__main__.py
# expect: identical hashes

# 3) Hook gates the new golden (content sniff picks it up)
echo '{"tool_input":{"file_path":".claude/skills/bmgen-eca-author/references/examples/door_ecu.min.yaml"}}' \
  | .claude/hooks/bmgen-eca-parse-gate.sh
# expect: exit 0 + "ok" line

# 4) Static structural check
grep -q "08-pulse-done" .claude/skills/bmgen-eca-author/SKILL.md
grep -q "pulse" .claude/skills/bmgen-eca-author/SKILL.md
test -f .claude/skills/bmgen-eca-author/references/08-pulse-done.md
test -f .claude/skills/bmgen-eca-author/references/examples/seat_ecu.min.yaml
grep -q "service order" .claude/skills/bmgen-eca-author/references/02-subdomains.md
grep -q "edge memory" .claude/skills/bmgen-eca-author/references/03-field-graph.md
grep -q "parse green but still wrong" .claude/skills/bmgen-eca-author/references/07-errors-fix.md
```

Live Remotive smoke (pulse window, not just parse) lives under
`.claude/skills/bmgen-eca-live-test/ACCEPTANCE.md` — keep-stack-up + run script
contracts there.

## Manual NL smoke (human)

Left for interactive Claude Code session. Prompt:

> Viết ECU YAML schema_v2 cho cửa trượt: nhận TargetPosition, clamp min/max, mỗi 0.2s bước current_pos, publish CurrentPosition + IsMoving. Khi tới nơi thì pulse IsDone true ~200ms rồi trở về false.

Expect:
1. Skill engages (or user runs `/bmgen-eca-yaml …`)
2. Skill reads `08-pulse-done.md` and the door golden (pulse variant)
3. YAML emitted with `was_moving`, `done_pulse_left`, `done_pulse_ticks`, ordered `arm/publish/decay/latch` rules
4. `bmgen-eca parse` green (hook and/or skill)
5. No claim of DONE while red; if user also asks for live behavior, follow
   `bmgen-eca-live-test` acceptance for pulse-window verification

- [ ] S1 manual: NL smoke passes in interactive session