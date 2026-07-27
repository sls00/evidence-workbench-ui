export type Home = 'generator' | 'validation'

export type PreflightCheck = {
  id: string
  label: string
  severity: string
  status: 'ok' | 'warn' | 'blocker'
  error?: { code: string; message: string; hint: string } | null
}

export type Preset = {
  id: string
  label: string
  summary: string
  scenario?: string
  bias_profile?: string
  n?: number
  seed?: number
  config_relpath?: string
  default?: boolean
}

export type RunSnapshot = {
  status: string
  run_id: string
  home?: string
  preset_id?: string
  finding_title?: string | null
  finding_subtitle?: string | null
  config_hash?: string | null
  primary_report?: string | null
  pillars?: { name: string; state: string }[]
  verify_status?: string | null
  verify_breaks?: { reason?: string; index?: number }[]
  artifacts_missing?: boolean
  report_url?: string | null
  error?: { code: string; message: string; hint: string } | null
  created_at?: string
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) {
    let detail: unknown = null
    try {
      detail = await res.json()
    } catch {
      detail = await res.text()
    }
    const err = new Error(`API ${res.status}`) as Error & { status: number; detail: unknown }
    err.status = res.status
    err.detail = detail
    throw err
  }
  return res.json() as Promise<T>
}

export function fetchPreflight(home: Home) {
  return api<{ can_run: boolean; checks: PreflightCheck[]; error?: unknown }>(
    `/api/preflight?home=${home}`,
  )
}

export function fetchPresets(home: Home) {
  return api<{ presets: Preset[] }>(`/api/presets?home=${home}`)
}

export function startRun(home: Home, preset_id: string) {
  return api<{ run_id: string }>(`/api/runs`, {
    method: 'POST',
    body: JSON.stringify({ home, preset_id }),
  })
}

export function getRun(runId: string) {
  return api<RunSnapshot>(`/api/runs/${runId}`)
}

export function cancelRun(runId: string) {
  return api<RunSnapshot>(`/api/runs/${runId}/cancel`, { method: 'POST' })
}

export function listRuns(home: Home) {
  return api<{ runs: RunSnapshot[]; warnings: string[] }>(`/api/runs?home=${home}`)
}

export function reverify(runId: string) {
  return api<RunSnapshot>(`/api/runs/${runId}/reverify`, { method: 'POST' })
}

export type TimelineEvent = {
  id: string
  label: string
  detail?: Record<string, unknown>
  index?: number
}

export type TimelinePayload = {
  run_id: string
  home: string
  status: string
  empty: boolean
  source?: string | null
  events: TimelineEvent[]
  honesty?: string | null
  verify_status?: string | null
}

export type InspectField = { key: string; value: unknown }

export type InspectPane = {
  id: string
  title: string
  source: string
  fields: InspectField[]
}

export type InspectPayload = {
  run_id: string
  home: string
  status: string
  empty: boolean
  panes: InspectPane[]
  honesty?: string | null
}

export function fetchTimeline(runId: string) {
  return api<TimelinePayload>(`/api/runs/${runId}/timeline`)
}

export function fetchInspect(runId: string) {
  return api<InspectPayload>(`/api/runs/${runId}/inspect`)
}
