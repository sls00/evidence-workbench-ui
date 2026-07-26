# Evidence Workbench UI

Local **Evidence Workbench** — a dual-home review instrument that orchestrates [`synth-fin`](https://github.com/sls00/synth-fin) and [`ai-mrg-bench`](https://github.com/sls00/ai-mrg-bench) and presents their proof. CLI/SDK remain canonical. Memorable signal: *You can see the proof.*

![Evidence Workbench — Generator Console (locked C′ chrome)](docs/images/hero-generator-console.png)

<p align="center"><sub>Locked visual reference (C′ dual-stage). Copper = finding/proof; cool slate = chrome selection.</sub></p>

![Evidence Workbench — Validation Review](docs/images/hero-validation-review.png)

<p align="center"><sub>Validation home with OCC § nav, Re-verify, and verify-chain proof deck.</sub></p>

## What this is / is not

| Is | Is not |
| --- | --- |
| Local FastAPI + Vite/React shell | Multi-tenant GRC SaaS |
| Orchestrates engines; embeds reports | Shadow metrics / rewritten validators |
| Approach B dual home (Generator + Validation) | Streamlit forever / Next.js cre_uw clone |

## Quick start

```bash
uv sync --group dev
uv run evidence-workbench --home generator --fake-runners
# → http://127.0.0.1:8765/?home=generator
```

Hot-reload UI (API already running on `:8765`):

```bash
cd web && npm ci && npm run dev
```

Real engines (siblings keep their own uv envs):

```bash
export SYNTH_FIN_ROOT=../synth-fin AI_MRG_BENCH_ROOT=../ai-mrg-bench
uv run evidence-workbench --home generator
```

## Deep-links

With `evidence-workbench` on `PATH`:

```bash
synth-fin ui    # Generator Console
workbench ui    # Validation Review
```

PATH `exec` only — **no** reverse import from the SDKs.

## Layout

```
src/evidence_workbench/   # FastAPI, runners, locks, index, preflight
web/                      # Vite + React + TS (DESIGN.md tokens)
tests/                    # pytest API smoke (fake runners)
vendor/design/            # finalized.html + lock meta (CI-checked)
docs/                     # architecture + README imagery
```

## Status & runs

- `$EVIDENCE_RUNS_ROOT` default `./.evidence-runs/` (gitignored)
- Namespaces: `synth-fin/` · `ai-mrg-bench/` · single `index.jsonl`
- Run: `POST /api/runs` → **202** + poll; cancel → `incomplete`
- Status law: `ok` \| `failed` \| `qualified` \| `incomplete`

## Tests / CI

```bash
EVIDENCE_FAKE_RUNNERS=1 uv run pytest -q
cd web && npm ci && npm run build
```

GitHub Actions: Python smoke, web build, design-lock sha256 check.

## Design locks

- `DESIGN.md` — tokens, typography (Cabinet + Commit Mono), motion
- `vendor/design/finalized.html` — Slice A chrome SoT (sha256 pinned in CI)
- Do not redesign fonts/colors/layout without explicit approval

## Docs

- [Architecture overview](docs/architecture/overview.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- Deferred post–Slice A work: [TODOS.md](TODOS.md)

## License

[Blue Oak Model License 1.0.0](https://blueoakcouncil.org/license/1.0.0) — see [`LICENSE`](LICENSE).
