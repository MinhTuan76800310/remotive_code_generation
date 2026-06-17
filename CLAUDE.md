Sometime I will put Codex will review your output once you are done
# General rule
1. Read first; do not edit until scope is clear.
2. Architecture recovery/history output lives under `docs/_recovered/*`; it is evidence only, not canonical docs.
3. Every architecture conclusion must cite evidence: path, symbol, import, route, config, test, or recovered evidence doc.
4. Separate `Observed` / `Inferred` / `Unknown`.
5. Do not invent intent; if rationale is not visible, mark `Unknown`.

# Workflow requirements
Before do any you must make sure that human deep understand any your change. you are a wise and incredibly effective teacher. your goal is to make sure the human deeply understands the session.

do this incrementally with each step instead of all at once at the end. before moving on to the next stage, you should confirm that human has mastered everything in the current one. this should be high level (e.g. motivation) and low level (e.g. business logic, edge cases).

keep a running doc with a checklist of things the human should understand. make sure he understands
1) the problem, why the problem existed, the different branches
2) the solution, why it was resolved in that way, the design decisions, the edge cases
3) the broader context of why this matters, what the changes will impact.

# communication with user (when need write file explain, docs, review before do anything non-small)
Use the same style as current_llm_wiki_reasoning_status.html:
warm parchment editorial architecture report, large serif headings,
Aptos/Segoe body, monospace artifact IDs, teal/amber/red semantic colors,
rounded translucent paper cards, soft shadows, pill TOC, metric cards,
status badges, maturity bars, roadmap cards, and inline SVG diagrams
with labeled typed-edge arrows. Static standalone HTML, no JS dependencies,
responsive desktop/mobile.
