import { describe, expect, it } from 'vitest'
import {
  dismissKey,
  evaluateReviewPath,
  leadCopy,
  readDismissed,
  writeDismissed,
  type ReviewPathInput,
} from './reviewPath'

function base(partial: Partial<ReviewPathInput> = {}): ReviewPathInput {
  return {
    home: 'generator',
    canRun: true,
    presetId: 'bias_demo_1k',
    busy: false,
    active: null,
    ...partial,
  }
}

describe('leadCopy', () => {
  it('uses utility leads and path-complete override', () => {
    expect(leadCopy('generator', false)).toMatch(/^Generator —/)
    expect(leadCopy('validation', false)).toMatch(/^Validation —/)
    expect(leadCopy('generator', true)).toContain('Path complete')
  })
})

describe('dismiss storage', () => {
  it('reads and writes per-home keys', () => {
    const store: Record<string, string> = {}
    const storage = {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v
      },
      removeItem: (k: string) => {
        delete store[k]
      },
    } as Storage
    expect(dismissKey('generator')).toBe('ew.reviewPath.dismissed.generator')
    expect(readDismissed('generator', storage)).toBe(false)
    writeDismissed('generator', true, storage)
    expect(readDismissed('generator', storage)).toBe(true)
    expect(readDismissed('validation', storage)).toBe(false)
    writeDismissed('generator', false, storage)
    expect(readDismissed('generator', storage)).toBe(false)
  })
})

describe('evaluateReviewPath generator', () => {
  it('marks preflight current when blocked', () => {
    const { steps, allDone } = evaluateReviewPath(base({ canRun: false, presetId: '' }))
    expect(allDone).toBe(false)
    expect(steps[0].state).toBe('current')
    expect(steps[0].id).toBe('preflight')
  })

  it('advances through preset → run current when idle ready', () => {
    const { steps } = evaluateReviewPath(base())
    expect(steps.find((s) => s.id === 'preflight')?.state).toBe('done')
    expect(steps.find((s) => s.id === 'preset')?.state).toBe('done')
    expect(steps.find((s) => s.id === 'run')?.state).toBe('current')
  })

  it('keeps run current while busy', () => {
    const { steps } = evaluateReviewPath(
      base({
        busy: true,
        active: { status: 'running', finding_title: null },
      }),
    )
    expect(steps.find((s) => s.id === 'run')?.state).toBe('current')
    expect(steps.find((s) => s.id === 'finding')?.state).toBe('todo')
  })

  it('completes through proof on terminal generator run', () => {
    const { steps, allDone, lead } = evaluateReviewPath(
      base({
        active: {
          status: 'ok',
          finding_title: 'Subgroup gap +7.6pp',
          pillars: [
            { name: 'Privacy', state: 'pass' },
            { name: 'Utility', state: 'qualified' },
            { name: 'Fidelity', state: 'pass' },
          ],
          report_url: '/api/runs/x/report',
        },
      }),
    )
    expect(allDone).toBe(true)
    expect(lead).toContain('Path complete')
    expect(steps.every((s) => s.state === 'done')).toBe(true)
  })
})

describe('evaluateReviewPath validation', () => {
  it('requires verify_status for final step', () => {
    const mid = evaluateReviewPath(
      base({
        home: 'validation',
        presetId: 'gc_full',
        active: {
          status: 'ok',
          finding_title: 'Adverse impact flagged',
        },
      }),
    )
    expect(mid.steps.find((s) => s.id === 'finding')?.state).toBe('done')
    expect(mid.steps.find((s) => s.id === 'verify')?.state).toBe('current')

    const done = evaluateReviewPath(
      base({
        home: 'validation',
        presetId: 'gc_full',
        active: {
          status: 'ok',
          finding_title: 'Adverse impact flagged',
          verify_status: 'PASS',
        },
      }),
    )
    expect(done.allDone).toBe(true)
  })
})
