# evidence-workbench-ui

Local Evidence Workbench shell (FastAPI + Vite/React) that orchestrates `synth-fin` and `ai-mrg-bench` and presents their proof — for MRM reviewers and portfolio hiring demos. CLI/SDK engines stay canonical; this package presents evidence.

## Commands

```bash
uv sync --group dev                                    # install (engines NOT in this venv — pandas conflict)
EVIDENCE_FAKE_RUNNERS=1 uv run pytest -q               # test  (THE verification gate)
cd web && npm ci && npm run build                      # typecheck + SPA build (CI gate)
cd web && npm run test:e2e                             # Playwright golden paths (fake runners; CI gate)

uv run evidence-workbench --home generator --fake-runners   # dev server → http://127.0.0.1:8765
cd web && npm run dev                                       # SPA hot reload (API on :8765)
```

Real engines (sibling checkouts, separate uv envs):

```bash
export SYNTH_FIN_ROOT=../synth-fin AI_MRG_BENCH_ROOT=../ai-mrg-bench
uv run evidence-workbench --home generator
```

## Conventions

- **Read `DESIGN.md` before any visual/UI change** — Cabinet Grotesk + Commit Mono, copper finding / cool-slate chrome; locked reference `vendor/design/finalized.html` (sha256 checked in CI).
- **Engines via subprocess** — runners call `uv run --directory <root> …`; never `pip install` synth-fin or workbench into this env.
- **Status law** — terminal states are exactly `ok` | `failed` | `qualified` | `incomplete`; cancel must yield `incomplete` and reclaim the namespace lock.
- **Runs layout** — `$EVIDENCE_RUNS_ROOT` (default `./.evidence-runs/`) with namespaces `synth-fin/` and `ai-mrg-bench/` + `index.jsonl`.
- **Canonical runner protocol**: `src/evidence_workbench/runners/base.py` (`Runner`, `RunSnapshot`, cancel lifecycle).

## Do not

- `import` from `synth_fin` or `workbench` — orchestrate by child process only; deep-links (`synth-fin ui` / `workbench ui`) PATH-exec this binary, never the reverse.
- Redesign fonts, colors, layout, or reopen **Approach A|C / persona wedge** without explicit user approval.
- Recompute or shadow engine metrics in the UI — embed reports and hashes as produced by the engines.
- Commit `.evidence-runs/` artifacts or edit `vendor/design/finalized.html` without updating `FINALIZED.lock.json` and CI sha256.
