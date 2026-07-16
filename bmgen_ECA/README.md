# bmgen-eca

ECA `schema_v2` → Remotive Behavioral Model compiler.

Standalone product from recipe-based `remotive-bm-compiler/bmgen` — do **not** import `bmgen.*` recipes.

## Install

```bash
cd bmgen_ECA
pip install -e ".[dev]"
```

Generated BMs need `numpy` + the Remotive SDK at **runtime** (not compiler install deps).

## Usage

```bash
# list frozen diagnostic codes
bmgen-eca errors

# parse / dump IR summary
bmgen-eca parse tests/fixtures/schema_v2.yaml

# generate Remotive BM package
bmgen-eca generate tests/fixtures/schema_v2.yaml --out /tmp/out
# → /tmp/out/bmgen_generated/door_ecu/{__init__.py,__main__.py}

# verify generated package (syntax)
bmgen-eca verify /tmp/out/bmgen_generated/door_ecu
```

From monorepo root (fixture under workspace):

```bash
pip install -e bmgen_ECA
bmgen-eca generate workspace/passenger_welcome_eca/schema/schema_v2.yaml --out .
# → bmgen_generated/door_ecu/
```

## Dialect (schema_v2)

- Root: `apiVersion` + `ecu_mock.name` + `behavior:`
- Signals: `[Bus]Frame.Signal` (bus → Remotive `CanNamespace` name)
- Expr: `$state.x`, `$para.x`, `$[Bus]Frame.Signal`, `min`/`max`/`abs`, numeric ops
- Docs of error codes: `bmgen-eca errors` (frozen public contract)

## Design

See [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md).

## Tests

```bash
python -m pytest tests/ -v
```
