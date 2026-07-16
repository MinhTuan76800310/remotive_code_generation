#!/usr/bin/env bash
# PostToolUse Write|Edit → bmgen-eca parse for schema_v2 ECA YAML only.
# Exit 0: skip or green. Exit 2: feed stderr back to Claude (errors remain).
set -euo pipefail

input=$(cat)

# Extract file path from Claude Code hook JSON
file_path=$(python3 -c '
import json,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw)
except Exception:
    print(""); sys.exit(0)
# common shapes: tool_input.file_path or tool_input.path
ti=d.get("tool_input") or d.get("toolInput") or {}
p=ti.get("file_path") or ti.get("filePath") or ti.get("path") or ""
print(p)
' <<<"$input")

if [[ -z "${file_path}" ]]; then
  exit 0
fi

# Only YAML
case "${file_path}" in
  *.yaml|*.yml) ;;
  *) exit 0 ;;
esac

# Exclude recipe compiler tree and obvious non-ECA
case "${file_path}" in
  *remotive-bm-compiler*|*docker-compose*.yml|*docker-compose*.yaml|*/.github/*)
    exit 0 ;;
esac

# Include heuristics: known ECA locations OR content sniff
include=0
case "${file_path}" in
  *schema_v2.yaml|*bmgen_ECA/tests/fixtures/*|*workspace/*/schema/*|*/passenger_welcome_eca/*|*/bmgen-eca-author/references/examples/*)
    include=1 ;;
esac

if [[ "$include" -eq 0 && -f "$file_path" ]]; then
  if python3 -c '
import sys
p=sys.argv[1]
try:
    t=open(p,encoding="utf-8",errors="replace").read(4000)
except Exception:
    sys.exit(1)
sys.exit(0 if ("apiVersion:" in t and "ecu_mock:" in t and "behavior:" in t) else 1)
' "$file_path"; then
    include=1
  fi
fi

if [[ "$include" -eq 0 ]]; then
  exit 0
fi

if ! command -v bmgen-eca >/dev/null 2>&1; then
  echo "bmgen-eca-parse-gate: bmgen-eca not on PATH. Run: pip install -e bmgen_ECA" >&2
  exit 2
fi

set +e
out=$(bmgen-eca parse "$file_path" 2>&1)
rc=$?
set -e

if [[ $rc -ne 0 ]]; then
  echo "bmgen-eca-parse-gate: parse FAILED for $file_path" >&2
  echo "$out" >&2
  echo "bmgen-eca-parse-gate: fix all E_* (see skill references/07-errors-fix.md); task not DONE." >&2
  exit 2
fi

# green: keep transcript light
echo "bmgen-eca-parse-gate: ok $file_path"
echo "$out" | tail -n 1
exit 0
