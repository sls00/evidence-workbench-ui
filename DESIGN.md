# Design System — Evidence Workbench

## Product Context
- **What this is:** Local guided **Evidence Workbench** shell for portfolio productization of `synth-fin` + `ai-mrg-bench` (Approach B, D homes). UI orchestrates and presents; CLI/SDK remain canonical.
- **Who it's for:** Primary viewer = MRM / hiring reviewer (~15 min). Secondary = working model-risk analyst (fast-follow depth).
- **Space/industry:** Model risk / fair-lending evidence tooling — not multi-tenant GRC SaaS; not TanML-style no-code hide-the-pipeline.
- **Project type:** Local web workbench (instrument), not marketing site or CRE underwriting UI.
- **Memorable signal:** *You can see the proof.*
- **Source of truth (product/IA):** `~/.gstack/projects/portfolio/sls00-feat-p5-synth-fin-cre-design-20260725-171238.md` (office-hours APPROVED). Do not reopen persona/wedge/Approach A|C as end-state.

## Aesthetic Direction
- **Direction:** Instrument / utilitarian dark (review instrument, not SaaS marketing shell)
- **Decoration level:** Intentional — fine hairline grid + barely-there grain; no glow, glass, or purple haze
- **Mood:** Quiet surfaces, sharp type hierarchy, proof before charts. Serious local tool for serious review.
- **Default theme:** Dark. Light is supported as secondary.
- **Reference / anti-reference:** Steal craft discipline from `cre_uw_platform` only — do not clone its Next.js patterns. Beat notebook + static report; avoid Streamlit-as-forever and TanML upload wizards.
- **Locked visual reference (Slice A chrome):** `~/.gstack/projects/portfolio/designs/evidence-workbench-golden-20260725/finalized.html` (sha256 `da74c3aaaf0dc78c125222fcb8f75dd8a8fd0e8f615f7d1ee479f14597b00e7f`, locked 2026-07-26 via /design-html D6:A)
- **Prior specimens (non-authoritative):** `~/.gstack/projects/portfolio/designs/design-system-20260725/evidence-workbench-preview.html` (consultation preview); `variant-C.html` in the same golden folder (shotgun source for spacing)

## Typography
- **Display/Hero:** Cabinet Grotesk — brand “Evidence Workbench”, primary finding headline/number
- **Body / UI / Labels / Data / Hashes / Code:** Commit Mono — single operational face (SIL OFL; dark-mode weight 400 recommended)
- **Loading:** Cabinet via Fontshare (or self-host); Commit Mono via Fontsource / self-hosted woff2 (design download with baked settings)
- **No second mono.** Do not add Berkeley Mono, Google Sans Code, or IBM Plex as primary stack.
- **Evidence-token recognition (composition-first):**
  - Labeled integrity strip (manifest / verify-chain / ground-truth)
  - Evidence wells for hashes and chain digests (inset surface, 1px border, 2px accent left edge)
  - Optical roles inside Commit Mono: prose 14–16px/400; metrics +1 step / 500 + tabular nums; tokens 12–13px with slightly open tracking
  - Click-to-copy on tokens; noun-first copy (`config_hash`, `verify`, `run_id`)
- **Scale:** 12 / 14 / 16 / 20 / 28 / 40 — finding number at 28–40 in Cabinet Grotesk

## Color
- **Approach:** Restrained; color is rare and meaningful. Copper (`--accent`) is reserved for proof/finding focal, CTA, focus, and evidence-well edges. Cool slate (`--selection`) marks chrome selection and disclaimer edge so the finding stays visually central.
- **Dark (default)**

| Token | Hex | Role |
| --- | --- | --- |
| `--bg-canvas` | `#0E1114` | App / cockpit ground |
| `--bg-panel` | `#161B20` | Controls + Run library |
| `--bg-elevated` | `#1E252C` | Controls fields, finding stage |
| `--border` | `#2A333C` | Structure |
| `--text` | `#E8EAED` | Primary |
| `--text-muted` | `#9AA3AD` | Meta, labels |
| `--accent` | `#D4A574` | CTA, focus, finding/proof focal (copper) |
| `--selection` | `#7A93A8` | Chrome selection: Controls preset, active Run library row, disclaimer left edge |
| `--pass` | `#8FAF93` | Pass (always + text label) |
| `--fail` | `#D4726A` | Fail (+ text) |
| `--qualified` | `#D4A574` | Qualified — never fake green |
| `--disclaimer-bg` | `#1A1814` | Disclaimer strip |

- **Light (secondary)**

| Token | Hex | Role |
| --- | --- | --- |
| `--bg-canvas` | `#F4F5F6` | Cockpit (grey) |
| `--bg-panel` | `#FFFFFF` | Controls + Run library (white) |
| `--bg-elevated` | `#EEF0F2` | Elevated controls |
| `--border` | `#D5DAE0` | Structure |
| `--text` | `#161B20` | Primary |
| `--text-muted` | `#5C6670` | Meta |
| `--accent` | `#9A6B3C` | CTA / focus / finding proof focal |
| `--selection` | `#4D6578` | Chrome selection (preset / active run / disclaimer left edge) |
| `--pass` / `--fail` / `--qualified` | `#3F6B48` / `#B1433C` / `#9A6B3C` | Status |
| `--disclaimer-bg` | `#F7F1E8` | Disclaimer strip |

- **Semantic rule:** Status = color **and** text. No compliance-certified affordances; pass/fail is review-support only.
- **Accent vs selection:** Do not reuse copper for preset/active-run/disclaimer edges. Finding card uses copper tinted border + 2px left accent.

## Spacing
- **Base unit:** 8px
- **Density:** Comfortable — match locked `finalized.html` / shotgun C′ (do not inflate finding header height)
- **Scale:** 2xs(2) xs(4) sm(8) md(16) lg(24) xl(32) 2xl(48) 3xl(64)
- **Rails:** Controls ~260px expanded; Run library ~200px expanded; collapsed panel width ~7.5rem (keeps CONTROLS / RUN LIBRARY labels readable)
- **Border radius:** sm 2px / md 4px / lg 6px — almost sharp (instrument, not bubbly)
- **Finding card:** padding 14px; copper mix border + 2px left `--accent` edge
- **Pretext:** Vendored beside finalized for long-form report body later. Do **not** pin heights on finding headlines or disclaimers (caused awkward spacing in an earlier design-html pass).

## Layout
- **Approach:** Grid-disciplined workbench shell; one composition per home
- **Golden-path composition (locked C′):** **Dual-stage cockpit**
  - **Upper (claim stage):** disclaimer → finding → pillars (Generator) or OCC §I–VII nav (Validation)
  - **Lower (proof deck):** integrity / verify-chain well (+ chain segments on Validation)
- **Default panel state on load:** Controls **expanded**; Run library **collapsed** (compact summary). Toggles remain Cursor-like.
- **Regions:** Brand header → home tabs → preflight bar → Controls | Evidence cockpit | Run library → sticky keymap footer
- **Brand:** “Evidence Workbench” is header-scale (Cabinet), not an eyebrow
- **Collapsible panels (Cursor-like):**
  - Toggle on Controls and Run library headers; shortcuts `[` / `]`
  - Icon geometry fixed; small pane **filled when expanded**, **clear when collapsed** (`aria-expanded`)
  - Collapsed body is a **compact summary** (preset + Run / active run id + count) — never a width-truncated full form
- **Homes:**
  - **Generator Console (synth-fin):** presets → Run → disclaimer → finding (ground-truth bias) → pillars → integrity well → report (HTML iframe; disclaimer also outside iframe)
  - **Validation Review (ai-mrg-bench):** presets → Run / Re-verify → §I+§II pinned → finding → OCC §I–VII nav → verify-chain well
- **Disclaimer / evidence hierarchy (strict):**
  1. Header meta (local · review-support only · not a compliance determination)
  2. Home disclaimer strip above finding (left edge = `--selection`)
  3. Primary finding (copper focal border)
  4. Status chips / verify-chain
  5. Full report body
  6. Charts last

## Motion
- **Approach:** Intentional (exactly three)
  1. **Preflight cascade** — checks resolve L→R; Run disabled until blockers clear
  2. **Finding settle** — ~250ms ease-out after run; reduced-motion → instant
  3. **Verify-chain pulse** — segment state change only; no confetti
- **Easing:** enter(ease-out) exit(ease-in) move(ease-in-out)
- **Duration:** micro(50–100ms) short(150–250ms) medium(250–400ms) long(400–700ms)
- **`prefers-reduced-motion`:** required

## Interaction — Keyboard-parity
- Every primary action is clickable **and** keyable; shortcut shown on the control
- Sticky footer keymap always visible (pattern from commitmono.com)
- Suggested map: `1`/`2` homes · `[`/`]` panels · `r` Run · `v` Re-verify · `c` copy token · `t` theme
- Focus rings use `--accent`; no keyboard traps; respect browser shortcuts

## Accessibility
- WCAG AA contrast on default dark pairs
- Status never color-only
- Keyboard-reachable: home tabs, Run, Re-verify, library rows, panel toggles
- Reduced motion; visible focus

## Shell / packaging lean (for eng-review)
| ID | Lean |
| --- | --- |
| **P1** | Sibling package `evidence-workbench` / `evid-wb-ui` depending on both SDKs via path/extras |
| **P2** | Local web: FastAPI orchestrator + Vite/React/TS frontend — not Streamlit forever; not Next.js/`cre_uw` clone |
| **P3** | One process; deep-links (`synth-fin ui` → Generator; `workbench ui` → Validation) |
| **P4** | Shared run index under `$EVIDENCE_RUNS_ROOT` (default `./.evidence-runs/`) with namespaces |

Slice A = shared chrome implementing these tokens + locked `finalized.html` composition. Decompose implementation in `/plan-eng-review`.

## SAFE / RISK (locked)
- **SAFE:** Persistent disclaimers; preflight before Run; labeled pass/fail/qualified; thin run library always present
- **RISKS taken:** Copper accent on ink dark for proof/finding only; cool-slate selection for chrome; finding-as-hero (charts demoted); manifest/verify as first-class chrome; full Commit Mono operations face; keyboard-parity as product feature; dual-stage cockpit

## Decisions Log
| Date | Decision | Rationale |
| --- | --- | --- |
| 2026-07-25 | Initial design system via /design-consultation | Locked to office-hours Evidence Workbench SoT; dark instrument; Cabinet + Commit; composition-first tokens; keyboard-parity; P1/P2 lean |
| 2026-07-25 | Dark mode default | User preference |
| 2026-07-25 | Cabinet Grotesk + Commit Mono only | Coherent claim/instrument split; no second mono |
| 2026-07-25 | Composition-first token recognition | Proof objects via wells/labels/size, not extra typefaces |
| 2026-07-25 | Keyboard-parity principle | Bridging CLI roots and 15-min GUI reviewers |
| 2026-07-25 | Collapsible Controls / Run library | Cursor-like; collapsed = compact summary; icon pane fill toggles |
| 2026-07-25 | Light: grey cockpit / white side panels | Restored after trial invert |
| 2026-07-25 | Shotgun C′ dual-stage + A finding copper border | Approved visual direction for golden paths |
| 2026-07-25 | `--selection` cool slate vs copper `--accent` | Finding stays focal; preset + active run + disclaimer edge still signal without copper competition |
| 2026-07-26 | `/design-html` finalized.html locked (D6:A) | Production HTML reference = shotgun C′ spacing; Pretext deferred for short finding/disclaimer text |
