# Architecture — Evidence Workbench UI (Slice A)

```
┌─ evidence-workbench (one uvicorn process) ─────────────────────┐
│  FastAPI: /api/preflight /api/runs /api/runs/{id} /report …    │
│  SPA: web/dist (prod) · Vite proxy (dev)                       │
│  Per-namespace single-flight lock (pid + heartbeat reclaim)    │
└───────────────┬──────────────────────────┬─────────────────────┘
                │ child process            │ child process
                ▼                          ▼
        synth-fin CLI              ValidationRun + verify
        generate→validate→report   (uv run --directory sibling)
                │                          │
                └──── {EVIDENCE_RUNS_ROOT}/{ns}/{run_id}/ ────┘
                           index.jsonl (terminal append only)
```

## Why engines are not pip-deps here

`synth-fin` requires `pandas>=3` while `workbench` (via aequitas) requires `pandas<3`. Slice A therefore invokes engines with `uv run --directory <root>` against sibling checkouts discovered via env / import / portfolio layout — not co-installed into this venv.

## Status law

`ok` | `failed` | `qualified` | `incomplete`  
(`qualified_pass` → `qualified`; cancel / stale reclaim → `incomplete`; never fake PASS from a torn audit DB)

## Related repos

| Repo | Role |
| --- | --- |
| `sls00/evidence-workbench-ui` (this) | Orchestrator + chrome |
| `sls00/synth-fin` | Generator engine + `synth-fin ui` deep-link |
| `sls00/ai-mrg-bench` | Validation engine + `workbench ui` deep-link |
