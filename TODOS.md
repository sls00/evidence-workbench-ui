# TODOS

Deferred work for Evidence Workbench (`evid-wb-ui`). Slice A implementation tasks live in the eng-review plan — this file tracks **post–Slice A** follow-through only.

Source plan: `~/.gstack/projects/portfolio/sls00-evidence-workbench-eng-review-20260726-003539.md`

## Slice B

### Live stage progress (SDK events)

**What:** When synth-fin / workbench SDKs expose stage events, wire optional live Run-stage progress (manifest/audit timeline) — replace post-hoc-only busy spinner.

**Why:** Office-hours Slice B lists optional live progress if SDKs gain stage events; without a TODO, implementers may invent fake percent-complete that hides the pipeline.

**Context:** Slice A deliberately has no stage streaming (202 + coarse poll only). Do not fabricate progress. Blocked until engines emit real stage events; then extend `Runner` poll snapshot or add an event channel. Keep DESIGN.md motion set (no confetti).

**Effort:** L  
**Priority:** P3  
**Depends on:** SDK stage-event design in `synth-fin` / `workbench`; Slice A runners stable  
**Blocked by:** No stage-event API in engines today

## Completed

### Review Mode narrative (Slice D)

**What:** Claim-stage Review path checklist (per-home, observe-state steps, first-visit auto-open + Hide dismiss + `?` reopen) inside Approach B chrome — not Approach C as product.

**Why:** Office-hours stretch post-B; hiring-reviewer orientation without new IA / live % / auto-Run.

**Shipped:** 2026-07-28 on `feat/slice-d`. Eng+design plan: `~/.gstack/projects/portfolio/sls00-evidence-workbench-slice-d-eng-review-20260728.md`.

### Same-home run compare (Slice C)

**What:** Same-home compare of ≤2 runs: side-by-side config/preset + JSON textual diff of `validation.json` or `bias_battery_summary.json` + verify status — not pixel HTML diff.

**Why:** Office-hours Slice C workbench depth; library pick-two → compare pane in dual-stage chrome.

**Shipped:** 2026-07-27 on `feat/slice-c`. API `GET /api/runs/compare`; library shift+select; Playwright golden path.

### Playwright golden-path E2E (Slice B1)

**What:** Playwright coverage for both ≤3-click golden paths (Generator `bias_demo_1k`, Validation `gc_full`) plus preflight-blocked Run, cancel→incomplete, and library reopen — fake runners default in CI (`web/e2e/`, `npm run test:e2e`).

**Why:** Durable regression coverage for hiring-demo paths after Slice A API smoke.

**Shipped:** 2026-07-27 on `feat/slice-b` (B1). Optional `@real-engines` remains B5 (local/nightly).
