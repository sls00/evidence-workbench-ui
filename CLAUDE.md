# evid-wb-ui — Evidence Workbench UI package

Product and design locks for the Evidence Workbench. Slice A implementation lives here
(`evidence-workbench` FastAPI + Vite/React).

## Design System
Always read `DESIGN.md` before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match `DESIGN.md`.

**Locked visual reference:** `vendor/design/finalized.html` (C′ dual-stage; copper finding; cool-slate selection chrome).
Also: `~/.gstack/projects/portfolio/designs/evidence-workbench-golden-20260725/finalized.html`

## Product locks (Evidence Workbench)
- Office-hours SoT: `~/.gstack/projects/portfolio/sls00-feat-p5-synth-fin-cre-design-20260725-171238.md`
- Design consultation artifact: `~/.gstack/projects/portfolio/evidence-workbench-design-consultation-20260725.md`
- Shotgun + design-html lock: `~/.gstack/projects/portfolio/designs/evidence-workbench-golden-20260725/approved.json`
- Eng plan: `~/.gstack/projects/portfolio/sls00-evidence-workbench-eng-review-20260726-003539.md`
- Do not reopen persona/wedge/Approach A|C as end-state without explicit user request.

## Packaging (locked P1–P4)
- Dist name `evidence-workbench`; engines invoked via `uv run --directory` (pandas conflict).
- Deep-links: `synth-fin ui` / `workbench ui` → PATH exec (no reverse import).
- `$EVIDENCE_RUNS_ROOT` default `./.evidence-runs/`.
