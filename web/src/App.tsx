import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import {
  cancelRun,
  fetchCompare,
  fetchInspect,
  fetchPreflight,
  fetchPresets,
  fetchTimeline,
  getRun,
  listRuns,
  reverify,
  startRun,
  type ComparePayload,
  type Home,
  type InspectPayload,
  type PreflightCheck,
  type Preset,
  type RunSnapshot,
  type TimelinePayload,
} from './api'
import {
  evaluateReviewPath,
  readDismissed,
  stepMark,
  writeDismissed,
} from './reviewPath'

const OCC_SECTIONS = ['§I', '§II', '§III', '§IV', '§V', '§VI', '§VII'] as const

function homeFromUrl(): Home {
  const q = new URLSearchParams(window.location.search).get('home')
  return q === 'validation' ? 'validation' : 'generator'
}

function setHomeUrl(home: Home) {
  const url = new URL(window.location.href)
  url.searchParams.set('home', home)
  window.history.replaceState({}, '', url)
}

function PanelToggle({
  expanded,
  onToggle,
  label,
}: {
  expanded: boolean
  onToggle: () => void
  label: string
}) {
  return (
    <button
      className="panel-toggle"
      type="button"
      aria-expanded={expanded}
      title={`Toggle ${label}`}
      aria-label={`Toggle ${label}`}
      onClick={onToggle}
    >
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <rect x="1.5" y="1.5" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.25" />
        <line x1="5.5" y1="1.5" x2="5.5" y2="14.5" stroke="currentColor" strokeWidth="1.25" />
        <rect className="pane-fill" x="1.5" y="1.5" width="4" height="13" />
      </svg>
    </button>
  )
}

function StatusDot({ state }: { state: string }) {
  const cls =
    state === 'ok' || state === 'pass'
      ? 'pass'
      : state === 'failed' || state === 'fail'
        ? 'fail'
        : 'qualified'
  const label =
    state === 'ok' || state === 'pass'
      ? 'pass'
      : state === 'failed' || state === 'fail'
        ? 'fail'
        : state === 'qualified'
          ? 'qualified'
          : state
  return (
    <span className="chip-status">
      <span className={`dot ${cls}`} />
      {label}
    </span>
  )
}

function copyText(text: string, toast: (m: string) => void) {
  void navigator.clipboard.writeText(text).then(
    () => toast('Copied'),
    () => toast('Copy failed'),
  )
}

function downloadReport(runId: string) {
  const a = document.createElement('a')
  a.href = `/api/runs/${runId}/report?download=1`
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

function formatInspectValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

const RAIL_DEFAULT = 260
const LIB_DEFAULT = 200
const RAIL_MIN = 200
const RAIL_MAX = 480
const LIB_MIN = 160
const LIB_MAX = 420
const COCKPIT_MIN = 320

function readStoredWidth(key: string, fallback: number): number {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    const n = Number(raw)
    return Number.isFinite(n) ? n : fallback
  } catch {
    return fallback
  }
}

function PanelResizer({
  side,
  onDrag,
}: {
  side: 'rail' | 'library'
  onDrag: (clientX: number) => void
}) {
  return (
    <div
      className={`panel-resizer panel-resizer--${side}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={side === 'rail' ? 'Resize Controls panel' : 'Resize Run library panel'}
      onPointerDown={(ev) => {
        ev.preventDefault()
        const target = ev.currentTarget
        target.setPointerCapture(ev.pointerId)
        const move = (e: PointerEvent) => onDrag(e.clientX)
        const up = (e: PointerEvent) => {
          target.releasePointerCapture(e.pointerId)
          target.removeEventListener('pointermove', move)
          target.removeEventListener('pointerup', up)
          target.removeEventListener('pointercancel', up)
          document.body.classList.remove('is-panel-resizing')
        }
        document.body.classList.add('is-panel-resizing')
        target.addEventListener('pointermove', move)
        target.addEventListener('pointerup', up)
        target.addEventListener('pointercancel', up)
      }}
    />
  )
}

export default function App() {
  const [home, setHome] = useState<Home>(homeFromUrl)
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [railOpen, setRailOpen] = useState(true)
  const [libOpen, setLibOpen] = useState(false)
  const [railW, setRailW] = useState(() => readStoredWidth('ew.railW', RAIL_DEFAULT))
  const [libW, setLibW] = useState(() => readStoredWidth('ew.libW', LIB_DEFAULT))
  const [checks, setChecks] = useState<PreflightCheck[]>([])
  const [canRun, setCanRun] = useState(false)
  const [presets, setPresets] = useState<Preset[]>([])
  const [presetId, setPresetId] = useState('')
  const [active, setActive] = useState<RunSnapshot | null>(null)
  const [library, setLibrary] = useState<RunSnapshot[]>([])
  const [libWarnings, setLibWarnings] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [settle, setSettle] = useState(false)
  const [toast, setToast] = useState('')
  const [occ, setOcc] = useState<(typeof OCC_SECTIONS)[number]>('§I')
  const [errorBanner, setErrorBanner] = useState<string | null>(null)
  const [timeline, setTimeline] = useState<TimelinePayload | null>(null)
  const [inspect, setInspect] = useState<InspectPayload | null>(null)
  const [compareSelection, setCompareSelection] = useState<string[]>([])
  const [compare, setCompare] = useState<ComparePayload | null>(null)
  const [libGuideOpen, setLibGuideOpen] = useState(true)
  const [reviewPathOpen, setReviewPathOpen] = useState(() => !readDismissed(homeFromUrl()))

  const showToast = useCallback((m: string) => {
    setToast(m)
    window.setTimeout(() => setToast(''), 1500)
  }, [])

  const selected = useMemo(
    () => presets.find((p) => p.id === presetId) || presets[0],
    [presets, presetId],
  )

  const refreshMeta = useCallback(async (h: Home) => {
    const [pf, pr, lib] = await Promise.all([
      fetchPreflight(h),
      fetchPresets(h),
      listRuns(h),
    ])
    setChecks(pf.checks)
    setCanRun(pf.can_run)
    setPresets(pr.presets)
    const def = pr.presets.find((p) => p.default) || pr.presets[0]
    setPresetId((cur) => (pr.presets.some((p) => p.id === cur) ? cur : def?.id || ''))
    setLibrary(lib.runs)
    setLibWarnings(lib.warnings || [])
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    document.documentElement.setAttribute('data-variant', 'C')
  }, [theme])

  useEffect(() => {
    setHomeUrl(home)
    setActive(null)
    setTimeline(null)
    setInspect(null)
    setCompareSelection([])
    setCompare(null)
    setErrorBanner(null)
    // Per-home dismiss: auto-open only when not dismissed for this home
    setReviewPathOpen(!readDismissed(home))
    void refreshMeta(home).catch((e) => setErrorBanner(String(e)))
  }, [home, refreshMeta])

  const reviewPath = useMemo(
    () =>
      evaluateReviewPath({
        home,
        canRun,
        presetId,
        busy,
        active,
      }),
    [home, canRun, presetId, busy, active],
  )

  const setReviewPathExpanded = useCallback(
    (open: boolean, opts?: { dismiss?: boolean }) => {
      setReviewPathOpen(open)
      if (opts?.dismiss) writeDismissed(home, true)
    },
    [home],
  )

  const toggleReviewPath = useCallback(() => {
    setReviewPathOpen((v) => !v)
  }, [])

  const loadPostRun = useCallback(async (runId: string) => {
    try {
      const [tl, insp] = await Promise.all([fetchTimeline(runId), fetchInspect(runId)])
      setTimeline(tl)
      setInspect(insp)
    } catch {
      setTimeline(null)
      setInspect(null)
    }
  }, [])

  // Load post-run timeline/inspect whenever a terminal run is active
  useEffect(() => {
    if (!active?.run_id) {
      setTimeline(null)
      setInspect(null)
      return
    }
    if (['running', 'queued', 'accepted'].includes(active.status)) {
      setTimeline(null)
      setInspect(null)
      return
    }
    void loadPostRun(active.run_id)
  }, [active?.run_id, active?.status, loadPostRun])

  const toggleCompareSelect = useCallback((runId: string) => {
    setCompareSelection((prev) => {
      if (prev.includes(runId)) {
        return prev.filter((id) => id !== runId)
      }
      if (prev.length >= 2) {
        return [prev[1], runId]
      }
      return [...prev, runId]
    })
  }, [])

  useEffect(() => {
    if (compareSelection.length !== 2) {
      setCompare(null)
      return
    }
    const [left, right] = compareSelection
    void fetchCompare(home, left, right)
      .then(setCompare)
      .catch(() => setCompare(null))
  }, [compareSelection, home])

  // Poll active run
  useEffect(() => {
    if (!active?.run_id || !['running', 'queued', 'accepted'].includes(active.status)) return
    const t = window.setInterval(() => {
      void getRun(active.run_id).then((snap) => {
        setActive(snap)
        if (!['running', 'queued'].includes(snap.status)) {
          setBusy(false)
          setSettle(true)
          window.setTimeout(() => setSettle(false), 300)
          void refreshMeta(home)
        }
      })
    }, 400)
    return () => window.clearInterval(t)
  }, [active?.run_id, active?.status, home, refreshMeta])

  const onRun = useCallback(async () => {
    if (!canRun || busy || !presetId) return
    setBusy(true)
    setErrorBanner(null)
    try {
      const { run_id } = await startRun(home, presetId)
      const snap = await getRun(run_id)
      setActive(snap)
      setLibOpen(true)
    } catch (e) {
      setBusy(false)
      const err = e as Error & { status?: number; detail?: { detail?: { error?: { message?: string } } } }
      const msg =
        err.detail && typeof err.detail === 'object'
          ? JSON.stringify(err.detail)
          : String(e)
      setErrorBanner(msg)
    }
  }, [busy, canRun, home, presetId])

  const onCancel = useCallback(async () => {
    if (!active?.run_id) return
    const snap = await cancelRun(active.run_id)
    setActive(snap)
    setBusy(false)
    void refreshMeta(home)
  }, [active?.run_id, home, refreshMeta])

  const onReverify = useCallback(async () => {
    if (!active?.run_id || home !== 'validation') return
    const snap = await reverify(active.run_id)
    setActive((prev) => ({ ...(prev || snap), ...snap, run_id: active.run_id }))
    showToast(`Verify ${snap.verify_status || 'done'}`)
  }, [active?.run_id, home, showToast])

  // Keyboard map
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      const tag = (ev.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (ev.key === '1') setHome('generator')
      if (ev.key === '2') setHome('validation')
      if (ev.key === '[') setRailOpen((v) => !v)
      if (ev.key === ']') setLibOpen((v) => !v)
      if (ev.key === 'r' || ev.key === 'R') void onRun()
      if (ev.key === 'v' || ev.key === 'V') void onReverify()
      if (ev.key === 't' || ev.key === 'T') setTheme((th) => (th === 'dark' ? 'light' : 'dark'))
      if (ev.key === '?') {
        ev.preventDefault()
        toggleReviewPath()
      }
      if (ev.key === 'c' || ev.key === 'C') {
        const token = active?.config_hash || active?.run_id
        if (token) copyText(token, showToast)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active?.config_hash, active?.run_id, onReverify, onRun, showToast, toggleReviewPath])

  const layoutClass = [
    'layout',
    'home',
    railOpen ? '' : 'rail-collapsed',
    libOpen ? '' : 'lib-collapsed',
  ]
    .filter(Boolean)
    .join(' ')

  const layoutStyle = {
    ...(railOpen ? ({ ['--rail-w']: `${railW}px` } as CSSProperties) : {}),
    ...(libOpen ? ({ ['--lib-w']: `${libW}px` } as CSSProperties) : {}),
  }

  const onResizeRail = useCallback((clientX: number) => {
    const layout = document.querySelector('.layout')
    if (!layout) return
    const rect = layout.getBoundingClientRect()
    const libPx = libOpen ? libW : 120
    const max = Math.min(RAIL_MAX, Math.floor(rect.width - libPx - COCKPIT_MIN))
    const next = Math.max(RAIL_MIN, Math.min(max, Math.round(clientX - rect.left)))
    setRailW(next)
    try {
      localStorage.setItem('ew.railW', String(next))
    } catch {
      /* ignore */
    }
  }, [libOpen, libW])

  const onResizeLib = useCallback((clientX: number) => {
    const layout = document.querySelector('.layout')
    if (!layout) return
    const rect = layout.getBoundingClientRect()
    const railPx = railOpen ? railW : 120
    const max = Math.min(LIB_MAX, Math.floor(rect.width - railPx - COCKPIT_MIN))
    const next = Math.max(LIB_MIN, Math.min(max, Math.round(rect.right - clientX)))
    setLibW(next)
    try {
      localStorage.setItem('ew.libW', String(next))
    } catch {
      /* ignore */
    }
  }, [railOpen, railW])

  const reportSrc =
    active?.run_id && active.report_url && !active.artifacts_missing
      ? `${active.report_url}?theme=${theme}`
      : null

  return (
    <div className="app">
      <div className="shell">
        <div className="shell-header">
          <div className="shell-brand">Evidence Workbench</div>
          <div className="shell-meta">local · review-support only · not a compliance determination</div>
        </div>

        <div className="shell-tabs" role="tablist">
          <button
            className={`shell-tab${home === 'generator' ? ' active' : ''}`}
            role="tab"
            type="button"
            aria-selected={home === 'generator'}
            onClick={() => setHome('generator')}
          >
            Home: Generator Console (synth-fin)
          </button>
          <button
            className={`shell-tab${home === 'validation' ? ' active' : ''}`}
            role="tab"
            type="button"
            aria-selected={home === 'validation'}
            onClick={() => setHome('validation')}
          >
            Home: Validation Review (ai-mrg-bench)
          </button>
        </div>

        <div className="preflight" aria-live="polite">
          {checks.map((c, i) => (
            <span
              key={c.id}
              className={`pf ${c.status === 'ok' ? 'ok' : c.status === 'warn' ? 'warn' : ''}`}
              style={{
                color: c.status === 'blocker' ? 'var(--fail)' : undefined,
                animationDelay: `${i * 40}ms`,
              }}
              title={c.error?.hint || c.error?.message || undefined}
            >
              {c.status === 'blocker' ? `[blocker] ${c.label}` : c.label}
            </span>
          ))}
        </div>

        <div className={layoutClass} data-home={home} style={layoutStyle}>
          <aside className="rail" aria-label="Controls">
            <div className="panel-head">
              <h3 className="region-h">Controls</h3>
              <PanelToggle expanded={railOpen} onToggle={() => setRailOpen((v) => !v)} label="Controls" />
            </div>
            <div className="panel-body panel-body--full">
              <label className="field-label">Preset</label>
              {presets.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className={`field${presetId === p.id ? ' selected' : ''}`}
                  onClick={() => setPresetId(p.id)}
                >
                  {p.summary || p.id}
                </button>
              ))}
              {home === 'generator' && selected && (
                <>
                  <label className="field-label">Scenario</label>
                  <div className="field">{selected.scenario}</div>
                  <label className="field-label">Bias profile</label>
                  <div className="field">{selected.bias_profile}</div>
                  <label className="field-label">n / seed</label>
                  <div className="field">
                    {selected.n} / {selected.seed}
                  </div>
                </>
              )}
              {home === 'validation' && selected && (
                <>
                  <label className="field-label">Config</label>
                  <div className="field">{selected.config_relpath}</div>
                </>
              )}
              <div style={{ marginTop: 14, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                <button
                  className="btn primary"
                  type="button"
                  data-action="run"
                  disabled={!canRun || busy}
                  onClick={() => void onRun()}
                >
                  {busy ? 'Running…' : 'Run demo'}
                  <span className="kbd">r</span>
                </button>
                {busy && (
                  <button
                    className="btn"
                    type="button"
                    data-action="cancel"
                    onClick={() => void onCancel()}
                  >
                    Cancel
                  </button>
                )}
                {home === 'validation' && (
                  <button
                    className="btn"
                    type="button"
                    data-action="reverify"
                    disabled={!active?.run_id || busy}
                    onClick={() => void onReverify()}
                  >
                    Re-verify<span className="kbd">v</span>
                  </button>
                )}
              </div>
              {!canRun && (
                <p style={{ marginTop: 12, fontSize: 11, color: 'var(--fail)' }}>
                  Run disabled until preflight blockers clear.
                </p>
              )}
            </div>
            <div className="panel-body panel-body--compact" aria-label="Controls summary">
              <div className="compact-card">
                <span className="k">Preset</span>
                <span className="v">{presetId || '—'}</span>
              </div>
              <button
                className="btn primary compact-run"
                type="button"
                disabled={!canRun || busy}
                onClick={() => void onRun()}
              >
                {busy ? '…' : 'Run'}
              </button>
              <div className="compact-blank">Full form hidden — expand Controls</div>
            </div>
            {railOpen && <PanelResizer side="rail" onDrag={onResizeRail} />}
          </aside>

          <main className="cockpit">
            <div className="stage-upper">
              <div className="review-path" data-testid="review-path" aria-label="Review path">
                <button
                  type="button"
                  className="review-path-toggle"
                  aria-expanded={reviewPathOpen}
                  aria-controls="review-path-body"
                  data-testid="review-path-toggle"
                  onClick={() => {
                    if (reviewPathOpen) setReviewPathExpanded(false, { dismiss: true })
                    else setReviewPathExpanded(true)
                  }}
                >
                  <svg
                    className="review-path-chevron"
                    viewBox="0 0 16 16"
                    aria-hidden="true"
                    data-expanded={reviewPathOpen ? 'true' : 'false'}
                  >
                    <path
                      d="M4 6l4 4 4-4"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <span className="review-path-label">Review path</span>
                  <span className="review-path-action">{reviewPathOpen ? 'Hide' : 'Show'}</span>
                </button>
                {reviewPathOpen && (
                  <div className="review-path-body" id="review-path-body" data-testid="review-path-body">
                    <p className="review-path-lead" data-testid="review-path-lead">
                      {reviewPath.lead}
                    </p>
                    <ol className="review-path-list" data-testid="review-path-steps">
                      {reviewPath.steps.map((step) => (
                        <li
                          key={step.id}
                          className="review-step"
                          data-state={step.state}
                          data-step-id={step.id}
                          aria-current={step.state === 'current' ? 'step' : undefined}
                        >
                          <span className="review-step-mark" aria-hidden="true">
                            {stepMark(step.state)}
                          </span>
                          <span className="review-step-label">
                            <strong>{step.title}</strong>
                            {step.detail ? ` — ${step.detail}` : ''}
                          </span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>

              <div className="disclaimer">
                Non-certification disclaimer (persistent): analytical / review-support only. Does not
                constitute legal advice or a determination of compliance.
              </div>

              {errorBanner && (
                <div className="disclaimer" style={{ borderLeftColor: 'var(--fail)', marginBottom: 12 }}>
                  {errorBanner}
                </div>
              )}

              {active?.artifacts_missing && (
                <div className="disclaimer" style={{ borderLeftColor: 'var(--qualified)' }}>
                  Artifacts missing — primary report not on disk. Row kept for honesty.
                </div>
              )}

              {active && active.status !== 'running' && active.finding_title ? (
                <div
                  className={`finding-card${settle ? ' settle' : ''}`}
                  data-testid="finding-card"
                  data-status={active.status}
                >
                  <div className="big" data-testid="finding-title">
                    {active.finding_title}
                  </div>
                  {active.finding_subtitle && <div className="sub">{active.finding_subtitle}</div>}
                  <div style={{ marginTop: 8 }}>
                    <StatusDot state={active.status} />
                    {active.verify_status && (
                      <span style={{ marginLeft: 8 }} data-testid="verify-chip">
                        <StatusDot state={active.verify_status === 'PASS' ? 'pass' : active.verify_status === 'FAIL' ? 'fail' : 'qualified'} />
                        <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--text-muted)' }}>
                          verify={active.verify_status}
                        </span>
                      </span>
                    )}
                  </div>
                </div>
              ) : busy ? (
                <div className="finding-card" data-testid="finding-card" data-status="running">
                  <div className="big" style={{ fontSize: 20 }}>
                    Running…
                  </div>
                  <div className="sub">Coarse status only — no live stage stream (Slice A)</div>
                </div>
              ) : reviewPathOpen ? null : (
                <div className="finding-card" data-testid="finding-card" data-status="idle">
                  <div className="big" style={{ fontSize: 20, color: 'var(--text-muted)' }}>
                    No run yet
                  </div>
                  <div className="sub">Select a preset and Run (≤3 clicks from deep-link).</div>
                </div>
              )}

              {home === 'generator' && active?.pillars && active.pillars.length > 0 && (
                <div className="pillars">
                  {active.pillars.map((p) => (
                    <div className="pillar" key={p.name}>
                      <strong>{p.name}</strong>
                      <span style={{ marginTop: 6, display: 'inline-block' }}>
                        <StatusDot state={p.state} />
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {home === 'validation' && (
                <div className="occ-nav" role="navigation" aria-label="OCC sections">
                  {OCC_SECTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      className={occ === s ? 'active' : ''}
                      onClick={() => setOcc(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}

              {compareSelection.length === 2 && compare && (
                <section className="post-run compare-section" aria-label="Run compare" data-testid="compare-pane">
                  <div className="post-run-block">
                    <p className="stage-label">
                      Compare · {compare.artifact_label}
                      {compare.identical ? ' · identical' : ''}
                    </p>
                    <div className="compare-meta">
                      <div className="inspect-well compare-side">
                        <p className="integrity-label">Left · {compare.left.preset_id}</p>
                        <div className="row">
                          <span className="noun">run_id</span>
                          <span className="val">{compare.left.run_id}</span>
                        </div>
                        <div className="row">
                          <span className="noun">config_hash</span>
                          <span className="val">{compare.left.config_hash || '—'}</span>
                        </div>
                        <div className="row">
                          <span className="noun">status</span>
                          <span className="val">
                            <StatusDot state={compare.left.status || 'ok'} />
                          </span>
                        </div>
                        {home === 'validation' && compare.left.verify_status && (
                          <div className="row">
                            <span className="noun">verify</span>
                            <span className="val">
                              <StatusDot
                                state={
                                  compare.left.verify_status === 'PASS'
                                    ? 'pass'
                                    : compare.left.verify_status === 'FAIL'
                                      ? 'fail'
                                      : 'qualified'
                                }
                              />
                              {compare.left.verify_status}
                            </span>
                          </div>
                        )}
                      </div>
                      <div className="inspect-well compare-side">
                        <p className="integrity-label">Right · {compare.right.preset_id}</p>
                        <div className="row">
                          <span className="noun">run_id</span>
                          <span className="val">{compare.right.run_id}</span>
                        </div>
                        <div className="row">
                          <span className="noun">config_hash</span>
                          <span className="val">{compare.right.config_hash || '—'}</span>
                        </div>
                        <div className="row">
                          <span className="noun">status</span>
                          <span className="val">
                            <StatusDot state={compare.right.status || 'ok'} />
                          </span>
                        </div>
                        {home === 'validation' && compare.right.verify_status && (
                          <div className="row">
                            <span className="noun">verify</span>
                            <span className="val">
                              <StatusDot
                                state={
                                  compare.right.verify_status === 'PASS'
                                    ? 'pass'
                                    : compare.right.verify_status === 'FAIL'
                                      ? 'fail'
                                      : 'qualified'
                                }
                              />
                              {compare.right.verify_status}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                    {compare.empty || !compare.diff_text ? (
                      <div className="compact-blank">
                        {compare.honesty || 'No diff — artifacts identical or unavailable.'}
                      </div>
                    ) : (
                      <pre className="compare-diff">{compare.diff_text}</pre>
                    )}
                    <button
                      className="btn"
                      type="button"
                      data-action="clear-compare"
                      style={{ marginTop: 8 }}
                      onClick={() => setCompareSelection([])}
                    >
                      Clear compare
                    </button>
                  </div>
                </section>
              )}

              {active && !['running', 'queued', 'accepted'].includes(active.status) && (
                <section className="post-run" aria-label="Post-run evidence">
                  <div className="post-run-block" data-testid="timeline-pane">
                    <p className="stage-label">
                      {home === 'generator' ? 'Manifest timeline' : 'Audit timeline'}
                      {timeline?.source ? ` · ${timeline.source}` : ''}
                    </p>
                    {timeline?.empty || !timeline?.events?.length ? (
                      <div className="compact-blank">
                        {timeline?.honesty || 'No timeline for this run.'}
                      </div>
                    ) : (
                      <ol className="timeline">
                        {timeline.events.map((ev) => (
                          <li key={`${ev.index}-${ev.id}`} className="timeline-row">
                            <span className="timeline-label">{ev.label}</span>
                            {ev.detail && Object.keys(ev.detail).length > 0 && (
                              <span className="timeline-detail">
                                {Object.entries(ev.detail)
                                  .slice(0, 3)
                                  .map(([k, v]) => `${k}=${formatInspectValue(v)}`)
                                  .join(' · ')}
                              </span>
                            )}
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>

                  <div className="post-run-block" data-testid="inspect-pane">
                    <p className="stage-label">Metric inspect · allowlisted artifacts</p>
                    {inspect?.empty || !inspect?.panes?.length ? (
                      <div className="compact-blank">
                        {inspect?.honesty || 'No inspect panes for this run.'}
                      </div>
                    ) : (
                      <div className="inspect-grid">
                        {inspect.panes.map((pane) => (
                          <div className="inspect-well" key={pane.id}>
                            <p className="integrity-label">
                              {pane.title}
                              <span className="inspect-source">{pane.source}</span>
                            </p>
                            {pane.fields.map((f) => (
                              <div className="row" key={f.key}>
                                <span className="noun">{f.key}</span>
                                <span className="val">{formatInspectValue(f.value)}</span>
                              </div>
                            ))}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </section>
              )}
            </div>

            <div className="stage-lower">
              <p className="stage-label">
                {home === 'generator' ? 'Proof deck · integrity' : 'Proof deck · verify-chain'}
              </p>
              <div className="proof-deck">
                <div className="well">
                  <p className="integrity-label">
                    {home === 'generator' ? 'Integrity' : 'Verify chain'}
                  </p>
                  <div className="row">
                    <span className="noun">run_id</span>
                    <span className="val">{active?.run_id || '—'}</span>
                    {active?.run_id && (
                      <button className="act" type="button" onClick={() => copyText(active.run_id, showToast)}>
                        Copy
                      </button>
                    )}
                  </div>
                  <div className="row">
                    <span className="noun">config_hash</span>
                    <span className="val">{active?.config_hash || '—'}</span>
                    {active?.config_hash && (
                      <button
                        className="act"
                        type="button"
                        onClick={() => copyText(active.config_hash!, showToast)}
                      >
                        Copy
                      </button>
                    )}
                  </div>
                  {home === 'validation' && (
                    <div className="row">
                      <span className="noun">verify</span>
                      <span className="val">{active?.verify_status || '—'}</span>
                      <span />
                    </div>
                  )}
                  {home === 'validation' && (active?.verify_breaks?.length || 0) > 0 && (
                    <div className="chain">
                      {active!.verify_breaks!.map((b, i) => (
                        <span className="seg" key={i}>
                          break: {b.reason || i}
                        </span>
                      ))}
                    </div>
                  )}
                  {home === 'validation' && active?.verify_status === 'PASS' && (
                    <div className="chain">
                      <span className="seg pass">chain PASS</span>
                    </div>
                  )}
                </div>
                <div>
                  {reportSrc ? (
                    <iframe
                      title="Report"
                      src={reportSrc}
                      style={{
                        width: '100%',
                        minHeight: 220,
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-md)',
                        background: 'var(--bg-elevated)',
                      }}
                    />
                  ) : (
                    <div className="compact-blank" style={{ minHeight: 120 }}>
                      Report embed when primary_report exists
                    </div>
                  )}
                </div>
              </div>
            </div>
          </main>

          <aside className="library" aria-label="Run library">
            <div className="panel-head">
              <h3 className="region-h">Run library</h3>
              <PanelToggle expanded={libOpen} onToggle={() => setLibOpen((v) => !v)} label="Run library" />
            </div>
            <div className="panel-body panel-body--full">
              <div className="library-instructions">
                <button
                  type="button"
                  className="library-instructions-toggle"
                  aria-expanded={libGuideOpen}
                  aria-controls="library-instructions-body"
                  data-testid="library-instructions-toggle"
                  onClick={() => setLibGuideOpen((v) => !v)}
                >
                  <svg
                    className="library-instructions-chevron"
                    viewBox="0 0 16 16"
                    aria-hidden="true"
                    data-expanded={libGuideOpen ? 'true' : 'false'}
                  >
                    <path
                      d="M4 6l4 4 4-4"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  <span className="library-instructions-label">Instructions</span>
                  <span className="library-instructions-action">{libGuideOpen ? 'Hide' : 'Show'}</span>
                </button>
                {libGuideOpen && (
                  <div
                    className="library-instructions-body"
                    id="library-instructions-body"
                    data-testid="library-instructions-body"
                  >
                    <p>
                      <strong>Click</strong> — reopen run (finding, timeline, inspect, report embed)
                    </p>
                    <p>
                      <strong>Shift+click</strong> — select up to 2 runs to compare
                    </p>
                    <p>
                      <strong>Double-click</strong> — download report file
                    </p>
                  </div>
                )}
              </div>
              {compareSelection.length > 0 && (
                <p className="compare-hint" data-testid="compare-hint">
                  Compare {compareSelection.length}/2 — shift+click runs to select
                </p>
              )}
              {library.length === 0 ? (
                <div className="compact-blank">No runs yet — first-run empty state</div>
              ) : (
                library.map((row) => (
                  <button
                    key={row.run_id}
                    type="button"
                    className={[
                      'run',
                      active?.run_id === row.run_id ? 'active' : '',
                      compareSelection.includes(row.run_id) ? 'compare-selected' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    data-testid="library-run"
                    data-run-id={row.run_id}
                    data-compare-selected={compareSelection.includes(row.run_id) ? 'true' : 'false'}
                    style={{ display: 'block', width: '100%', textAlign: 'left' }}
                    onClick={(ev) => {
                      if (ev.shiftKey) {
                        toggleCompareSelect(row.run_id)
                        return
                      }
                      void getRun(row.run_id).then(setActive)
                      if (row.artifacts_missing) showToast('Artifacts missing')
                    }}
                    onDoubleClick={(ev) => {
                      ev.preventDefault()
                      if (row.artifacts_missing) {
                        showToast('Artifacts missing')
                        return
                      }
                      downloadReport(row.run_id)
                      showToast('Downloading report')
                    }}
                  >
                    <div>
                      {row.preset_id} · {row.status}
                      {row.artifacts_missing ? ' · missing' : ''}
                    </div>
                    <div className="id">{row.run_id}</div>
                  </button>
                ))
              )}
              {libWarnings.length > 0 && (
                <p style={{ fontSize: 10, color: 'var(--qualified)', marginTop: 8 }}>
                  {libWarnings.join(' · ')}
                </p>
              )}
            </div>
            <div className="panel-body panel-body--compact" aria-label="Library summary">
              <div className="compact-card">
                <span className="k">Active</span>
                <span className="v">{active?.run_id || '—'}</span>
              </div>
              <div className="compact-card">
                <span className="k">Count</span>
                <span className="v">{library.length}</span>
              </div>
            </div>
            {libOpen && <PanelResizer side="library" onDrag={onResizeLib} />}
          </aside>
        </div>
      </div>

      <div className="keymap" aria-label="Keyboard shortcuts">
        <span>
          <kbd>1</kbd>/<kbd>2</kbd> homes
        </span>
        <span>
          <kbd>[</kbd>/<kbd>]</kbd> panels
        </span>
        <span>
          <kbd>?</kbd> Review path
        </span>
        <span>
          <kbd>r</kbd> Run
        </span>
        <span>
          <kbd>v</kbd> Re-verify
        </span>
        <span>
          <kbd>c</kbd> copy token
        </span>
        <span>
          <kbd>t</kbd> theme
        </span>
      </div>
      <div className={`toast${toast ? ' show' : ''}`} role="status">
        {toast}
      </div>
    </div>
  )
}
