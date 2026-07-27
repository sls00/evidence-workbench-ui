# TODOS

Deferred work for Evidence Workbench (`evid-wb-ui`). Slice A implementation tasks live in the eng-review plan — this file tracks **post–Slice A** follow-through only.

Source plan: `~/.gstack/projects/portfolio/sls00-evidence-workbench-eng-review-20260726-003539.md`

## Slice B

### Playwright golden-path E2E

**What:** Add Playwright coverage for both ≤3-click golden paths (Generator `bias_demo_1k`, Validation `gc_full`) plus preflight-blocked Run and cancel→incomplete.

**Why:** Office-hours / eng-review deferred browser E2E until packaging + chrome stabilize; without this TODO the hiring-demo paths lack durable regression coverage after Slice A API smoke.

**Context:** Slice A CI is unit + API smoke with fake runners (mandatory cancel test). Playwright should hit the real SPA against a local `evidence-workbench` server with fixtures/roots available. Start from the eng-review test plan QA artifact. Match DESIGN.md / `vendor/design/finalized.html` composition — do not redesign. Keys: `r` Run, home tabs, library reopen.

**Effort:** M  
**Priority:** P2  
**Depends on:** Slice A T5–T7 (API + chrome wired); optional real `@integration` roots/LFS for full engine paths

### Live stage progress (SDK events)

**What:** When synth-fin / workbench SDKs expose stage events, wire optional live Run-stage progress (manifest/audit timeline) — replace post-hoc-only busy spinner.

**Why:** Office-hours Slice B lists optional live progress if SDKs gain stage events; without a TODO, implementers may invent fake percent-complete that hides the pipeline.

**Context:** Slice A deliberately has no stage streaming (202 + coarse poll only). Do not fabricate progress. Blocked until engines emit real stage events; then extend `Runner` poll snapshot or add an event channel. Keep DESIGN.md motion set (no confetti).

**Effort:** L  
**Priority:** P3  
**Depends on:** SDK stage-event design in `synth-fin` / `workbench`; Slice A runners stable  
**Blocked by:** No stage-event API in engines today

## Slice C

### Same-home run compare

**What:** Same-home compare of ≤2 runs: side-by-side config/preset + JSON textual diff of `validation.json` or `bias_battery_summary.json` + verify status — not pixel HTML diff.

**Why:** Office-hours sequences compare as Slice C; workbench depth beyond reopen needs it for lasting adoptability after the hiring demo.

**Context:** Slice A run library is reopen-only. Index + artifact dirs already carry `preset_id`, `config_hash`, and `extra` paths. UI: pick two rows in one namespace; show diff + verify chips. Do not invent cross-home compare. Visual chrome stays DESIGN.md / finalized composition.

**Effort:** M  
**Priority:** P3  
**Depends on:** Slice A run library + index; Slice B inspect panes preferred but not strictly required

## Completed

_(none yet)_
