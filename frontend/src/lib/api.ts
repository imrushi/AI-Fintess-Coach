import type {
  CheckInRequest,
  CheckInResponse,
  GoalProgress,
  KpiMetrics,
  OverridePrompt,
  ReadinessReport,
  SchedulerStatus,
  TrainingPlan,
  TrainingSession,
  UserProfile,
} from './types'

// ── Supplementary response types ─────────────────────────────────────────

export interface PlanHistoryItem {
  plan_id: string
  valid_from: string
  valid_to: string
  training_gate: string
  generated_at: string
}

export interface ReadinessHistoryItem {
  report_date: string
  readiness_score: number
  readiness_label: string
  training_gate: string
  flags: string[]
}

export interface PipelineRunResult {
  success: boolean
  readiness_score: number | null
  training_gate: string | null
  plan_valid_from: string | null
  plan_valid_to: string | null
  session_count: number | null
  total_tokens_used: number | null
  error: string | null
}

// ── User ID helpers ───────────────────────────────────────────────────────

export const USER_ID_KEY = 'fitness_coach_user_id'

export function getStoredUserId(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(USER_ID_KEY)
}

export function storeUserId(id: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(USER_ID_KEY, id)
}

// ── Core fetch helper ─────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let message = 'API error'
    try {
      const data = await res.json()
      message = data.detail ?? data.error ?? message
    } catch {
      // ignore parse errors, use default message
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

// ── Plans ─────────────────────────────────────────────────────────────────

export async function getCurrentPlan(userId: string): Promise<TrainingPlan> {
  return apiFetch(`/plans/current/${userId}`)
}

export async function getSessionForDate(userId: string, date: string): Promise<TrainingSession> {
  return apiFetch(`/plans/${userId}/session/${date}`)
}

export async function getPlanHistory(userId: string, limit = 5): Promise<PlanHistoryItem[]> {
  return apiFetch(`/plans/history/${userId}?limit=${limit}`)
}

export async function getOverridePrompt(userId: string): Promise<OverridePrompt> {
  return apiFetch(`/plans/override-prompt/${userId}`)
}

// ── Analysis ──────────────────────────────────────────────────────────────

export async function getReadinessReport(userId: string, date?: string): Promise<ReadinessReport> {
  const qs = date ? `?report_date=${date}` : ''
  return apiFetch(`/analysis/report/${userId}${qs}`)
}

export async function getReadinessHistory(userId: string, days = 14): Promise<ReadinessHistoryItem[]> {
  return apiFetch(`/analysis/history/${userId}?days=${days}`)
}

// ── Check-in ──────────────────────────────────────────────────────────────

export async function submitCheckIn(data: CheckInRequest): Promise<CheckInResponse> {
  return apiFetch('/checkin', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getTodayCheckIn(userId: string): Promise<CheckInResponse | null> {
  const res = await fetch(`/api/checkin/today/${userId}`)
  if (res.status === 404) return null
  if (!res.ok) {
    let message = 'API error'
    try {
      const data = await res.json()
      message = data.detail ?? data.error ?? message
    } catch { /* ignore */ }
    throw new Error(message)
  }
  const body = await res.json()
  return body ?? null
}

// ── Pipeline ──────────────────────────────────────────────────────────────

export async function runFullPipeline(userId: string, overrideChoice?: string): Promise<PipelineRunResult> {
  return apiFetch('/pipeline/run', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, override_choice: overrideChoice ?? null }),
  })
}

// ── Profile ───────────────────────────────────────────────────────────────

export async function getProfile(userId: string): Promise<UserProfile> {
  return apiFetch(`/profile/${userId}`)
}

export async function updateProfile(userId: string, data: Partial<UserProfile>): Promise<UserProfile> {
  return apiFetch(`/profile/${userId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

// ── KPI Metrics ───────────────────────────────────────────────────────────

export async function getKpiMetrics(userId: string, days = 14): Promise<KpiMetrics> {
  return apiFetch(`/metrics/kpi/${userId}?days=${days}`)
}

export async function getGoalProgress(userId: string): Promise<GoalProgress> {
  return apiFetch(`/metrics/goal/${userId}`)
}

// ── Scheduler ─────────────────────────────────────────────────────────────

export async function getSchedulerStatus(): Promise<SchedulerStatus> {
  return apiFetch('/scheduler/status')
}

export async function triggerSync(userId: string): Promise<{ triggered: boolean; message: string }> {
  return apiFetch('/scheduler/trigger/sync', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  })
}

export async function triggerPipeline(userId: string): Promise<{ triggered: boolean }> {
  return apiFetch('/scheduler/trigger/pipeline', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  })
}

export async function clearCurrentPlan(userId: string): Promise<{ cleared: boolean; plans_affected: number; message: string }> {
  return apiFetch(`/plans/current/${userId}`, { method: 'DELETE' })
}

export async function resetAllData(userId: string): Promise<{ reset: boolean; deleted: Record<string, number>; message: string; next_steps: string[] }> {
  return apiFetch(`/data/${userId}`, { method: 'DELETE' })
}
