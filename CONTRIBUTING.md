# Contributing — Evidence Workbench UI

## Scope
This repo is the **Evidence Workbench** shell (`evidence-workbench` package): FastAPI orchestrator + Vite/React UI for `synth-fin` and `ai-mrg-bench`. Engines stay in their sibling private repos; this package presents proof — no shadow metrics.

## Product / design locks
Do not reopen without an explicit request:
- Approach B dual-home chrome (Generator + Validation)
- Visual SoT: `DESIGN.md` + `vendor/design/finalized.html`
- Eng plan: Slice A MVP boundary (see README)

## Dev setup
```bash
uv sync --group dev
uv run evidence-workbench --home generator --fake-runners

# optional SPA hot reload
cd web && npm ci && npm run dev
```

## Tests
```bash
EVIDENCE_FAKE_RUNNERS=1 uv run pytest -q
cd web && npm run build
```

Mandatory smoke (already in CI): cancel → `incomplete` + lock reclaim.

## Branching
- `main` — protected integration branch
- `feat/…`, `fix/…` — short-lived branches; open **draft** PRs early
- Prefer one coherent Slice PR over drive-by refactors in engine repos

## Deep-links
Engine CLIs exec this binary by PATH name only (`synth-fin ui` / `workbench ui`). **Never** `import evidence_workbench` from those packages.

## License
[Blue Oak Model License 1.0.0](https://blueoakcouncil.org/license/1.0.0) — see `LICENSE`.
