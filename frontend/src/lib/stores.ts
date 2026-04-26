import { writable, derived } from 'svelte/store'
import type { TrainingPlan, ReadinessReport, OverridePrompt, UserProfile } from './types'
import { getStoredUserId } from './api'

// ── Writable stores ───────────────────────────────────────────────────────

export const userId = writable<string | null>(getStoredUserId())

export const currentPlan = writable<TrainingPlan | null>(null)

export const todayReport = writable<ReadinessReport | null>(null)

export const overridePrompt = writable<OverridePrompt | null>(null)

export const userProfile = writable<UserProfile | null>(null)

export const isLoading = writable<boolean>(false)

export const pipelineRunning = writable<boolean>(false)

export const globalError = writable<string | null>(null)

export const showOverrideModal = writable<boolean>(false)

// ── Toast system ──────────────────────────────────────────────────────────

export interface Toast {
  id: string
  message: string
  type: 'success' | 'error' | 'info'
  duration: number
}

export const toasts = writable<Toast[]>([])

export function addToast(
  message: string,
  type: Toast['type'] = 'info',
  duration = 4000,
): void {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  toasts.update(t => [...t, { id, message, type, duration }])
  if (duration > 0) {
    setTimeout(() => dismissToast(id), duration)
  }
}

export function dismissToast(id: string): void {
  toasts.update(t => t.filter(toast => toast.id !== id))
}

// ── Derived stores ────────────────────────────────────────────────────────

export const todaySession = derived(currentPlan, ($plan) => {
  if (!$plan) return null
  const today = new Date().toISOString().split('T')[0]
  return $plan.sessions.find(s => s.date === today) ?? null
})

export const tomorrowSession = derived(currentPlan, ($plan) => {
  if (!$plan) return null
  const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0]
  return $plan.sessions.find(s => s.date === tomorrow) ?? null
})

export const weekSessions = derived(currentPlan, ($plan) => {
  if (!$plan) return []
  const today = new Date()
  const monday = new Date(today)
  monday.setDate(today.getDate() - today.getDay() + 1)
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  const mondayStr = monday.toISOString().split('T')[0]
  const sundayStr = sunday.toISOString().split('T')[0]
  return $plan.sessions.filter(s => s.date >= mondayStr && s.date <= sundayStr)
})

// ── Reset helper ──────────────────────────────────────────────────────────

export function clearAllStores(): void {
  currentPlan.set(null)
  todayReport.set(null)
  overridePrompt.set(null)
  userProfile.set(null)
  isLoading.set(false)
  pipelineRunning.set(false)
  globalError.set(null)
  showOverrideModal.set(false)
}
