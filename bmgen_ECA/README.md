# bmgen-eca

ECA `schema_v2` → Remotive Behavioral Model compiler. Separate product from
`remotive-bm-compiler/bmgen` (recipe-based); do not import `bmgen.*` recipes.

```bash
pip install -e ".[dev]"
```

Generated BMs need `numpy` + the Remotive SDK at runtime (not compiler install deps).

See [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) for the frozen contracts.
