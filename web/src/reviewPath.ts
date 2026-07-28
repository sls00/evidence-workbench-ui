import type { Home } from './api'

export type StepState = 'todo' | 'current' | 'done'

export type ReviewStepId = 'preflight' | 'preset' | 'run' | 'finding' | 'proof' | 'verify'

export type ReviewStepView = {
  id: ReviewStepId
  title: string
  detail: string
  state: StepState
}

export type ReviewPathSnapshot = {
  status: string
  finding_title?: string | null
  pillars?: { name: string; state: string }[]
  verify_status?: string | null
  report_url?: string | null
  artifacts_missing?: boolean
}

export type ReviewPathInput = {
  home: Home
  canRun: boolean
  presetId: string
  busy: boolean
  active: ReviewPathSnapshot | null
}

const TERMINAL = new Set(['ok', 'failed', 'qualified', 'incomplete'])

export function dismissKey(home: Home): string {
  return `ew.reviewPath.dismissed.${home}`
}

export function readDismissed(home: Home, storage: Storage = localStorage): boolean {
  try {
    return storage.getItem(dismissKey(home)) === '1'
  } catch {
    return false
  }
}

export function writeDismissed(home: Home, dismissed: boolean, storage: Storage = localStorage): void {
  try {
    if (dismissed) storage.setItem(dismissKey(home), '1')
    else storage.removeItem(dismissKey(home))
  } catch {
    /* ignore quota / private mode */
  }
}

export function leadCopy(home: Home, allDone: boolean): string {
  if (allDone) return 'Path complete — Hide or press ?'
  return home === 'generator'
    ? 'Generator — preset → Run → finding → proof.'
    : 'Validation — preset → Run → finding → verify-chain.'
}

function isTerminal(status: string): boolean {
  return TERMINAL.has(status)
}

function isRunComplete(input: ReviewPathInput): boolean {
  if (input.busy) return false
  const st = input.active?.status
  return Boolean(st && isTerminal(st))
}

function isFindingComplete(input: ReviewPathInput): boolean {
  if (!isRunComplete(input)) return false
  return Boolean(input.active?.finding_title)
}

function isProofComplete(input: ReviewPathInput): boolean {
  if (!isFindingComplete(input)) return false
  const a = input.active
  if (!a || a.artifacts_missing) return false
  if (input.home === 'generator') {
    return Boolean(a.report_url) || Boolean(a.pillars && a.pillars.length > 0)
  }
  return Boolean(a.verify_status)
}

function isVerifyComplete(input: ReviewPathInput): boolean {
  if (!isFindingComplete(input)) return false
  return Boolean(input.active?.verify_status)
}

type Pred = (input: ReviewPathInput) => boolean

type StepSpec = {
  id: ReviewStepId
  title: string
  detail: (input: ReviewPathInput) => string
  done: Pred
}

const GENERATOR_STEPS: StepSpec[] = [
  {
    id: 'preflight',
    title: 'Preflight',
    detail: () => 'blockers clear; Run enabled',
    done: (i) => i.canRun,
  },
  {
    id: 'preset',
    title: 'Preset',
    detail: (i) => i.presetId || 'select preset',
    done: (i) => Boolean(i.presetId),
  },
  {
    id: 'run',
    title: 'Run',
    detail: () => 'press Run (r); wait for terminal status',
    done: isRunComplete,
  },
  {
    id: 'finding',
    title: 'Finding',
    detail: () => 'subgroup gap + pillars',
    done: isFindingComplete,
  },
  {
    id: 'proof',
    title: 'Proof',
    detail: () => 'integrity well + report',
    done: isProofComplete,
  },
]

const VALIDATION_STEPS: StepSpec[] = [
  {
    id: 'preflight',
    title: 'Preflight',
    detail: () => 'blockers clear; Run enabled',
    done: (i) => i.canRun,
  },
  {
    id: 'preset',
    title: 'Preset',
    detail: (i) => i.presetId || 'select preset',
    done: (i) => Boolean(i.presetId),
  },
  {
    id: 'run',
    title: 'Run',
    detail: () => 'press Run (r); wait for terminal status',
    done: isRunComplete,
  },
  {
    id: 'finding',
    title: 'Finding',
    detail: () => '§I/§II + primary finding',
    done: isFindingComplete,
  },
  {
    id: 'verify',
    title: 'Verify',
    detail: () => 'verify-chain well',
    done: isVerifyComplete,
  },
]

export function stepsForHome(home: Home): StepSpec[] {
  return home === 'generator' ? GENERATOR_STEPS : VALIDATION_STEPS
}

/** Observe workbench state → per-step todo/current/done. */
export function evaluateReviewPath(input: ReviewPathInput): {
  steps: ReviewStepView[]
  allDone: boolean
  lead: string
} {
  const specs = stepsForHome(input.home)
  const doneFlags = specs.map((s) => s.done(input))
  const firstIncomplete = doneFlags.findIndex((d) => !d)
  const allDone = firstIncomplete === -1
  const steps: ReviewStepView[] = specs.map((s, idx) => {
    let state: StepState = 'todo'
    if (doneFlags[idx]) state = 'done'
    else if (idx === firstIncomplete) state = 'current'
    return {
      id: s.id,
      title: s.title,
      detail: s.detail(input),
      state,
    }
  })
  return {
    steps,
    allDone,
    lead: leadCopy(input.home, allDone),
  }
}

export function stepMark(state: StepState): string {
  if (state === 'done') return '✓'
  if (state === 'current') return '→'
  return '○'
}
