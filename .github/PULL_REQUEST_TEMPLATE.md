---
name: Pull request
about: Changes to Evidence Workbench UI
labels: ''
---

## Summary
<!-- Why this change exists. Link eng plan / issue if relevant. -->

## Test plan
- [ ] `uv sync && uv run pytest -q` (fake runners; no LFS)
- [ ] `cd web && npm ci && npm run build`
- [ ] Manual: `evidence-workbench --home generator --fake-runners` → Run → finding settles
- [ ] (If engines) deep-link: `synth-fin ui` / `workbench ui` opens correct home

## Design / product locks
- [ ] No visual redesign vs `DESIGN.md` / `vendor/design/finalized.html`
- [ ] No reopen of persona/wedge/Approach A|C without explicit ask
