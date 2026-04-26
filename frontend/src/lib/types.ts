export interface HRVSignal {
  current_ms: number | null
  baseline_ms: number | null
  deviation_pct: number | null
  trend_3d: string | null
}

export interface SleepSignal {
  score: number | null
  duration_min: number | null
  deep_min: number | null
  rem_min: number | null
  quality_label: string | null
}

export interface LoadSignal {
  acwr: number | null
  acute_load: number | null
  chronic_load: number | null
  acwr_risk: string | null
}

export interface KeySignals {
  hrv: HRVSignal
  sleep: SleepSignal
  load: LoadSignal
  body_battery_morning: number | null
  resting_hr: number | null
  resting_hr_trend: string | null
  stress_avg: number | null
}

export interface ReadinessReport {
  report_date: string
  readiness_score: number
  readiness_label: 'EXCELLENT' | 'GOOD' | 'MODERATE' | 'POOR' | 'VERY_POOR'
  training_gate: 'PROCEED' | 'PROCEED_WITH_CAUTION' | 'REST_RECOMMENDED' | 'MANDATORY_REST'
  key_signals: KeySignals
  flags: string[]
  narrative: string
  recommendations: string[]
  data_completeness_pct: number
}

export interface NutritionGuidance {
  pre_session: string | null
  during_session: string | null
  post_session: string | null
  daily_notes: string | null
}

export type SportType = 'swim' | 'bike' | 'run' | 'brick' | 'strength' |
                        'yoga' | 'active_recovery' | 'rest'

export type IntensityZone = 'Z1' | 'Z2' | 'Z3' | 'Z4' | 'Z5'

export interface StrengthExercise {
  exercise: string
  sets: number
  reps_or_duration: string
  notes: string | null
}

export interface SwimSet {
  stroke: string
  distance_m: number
  reps: number
  rest_sec: number | null
  intensity: string | null
  notes: string | null
}

export interface TrainingSession {
  date: string
  day_of_week: string
  sport: SportType
  status: 'planned' | 'completed' | 'skipped' | 'modified'
  duration_min: number | null
  distance_m: number | null
  intensity_zone: IntensityZone | null
  title: string
  description: string
  key_focus: string
  exercises: StrengthExercise[]
  swim_sets: SwimSet[]
  nutrition: NutritionGuidance
  override_applied: string | null
  readiness_adjusted: boolean
}

export interface WeeklyTargets {
  week_number: number
  week_start: string
  total_volume_min: number
  long_session_sport: SportType | null
  key_workout: string | null
  weekly_theme: string | null
  intensity_distribution: Record<string, number>
}

export interface TrainingPlan {
  plan_id: string
  user_id: string
  generated_at: string
  valid_from: string
  valid_to: string
  goal_event: string | null
  goal_date: string | null
  weeks_to_goal: number | null
  sessions: TrainingSession[]
  weekly_targets: WeeklyTargets[]
  readiness_score_at_generation: number | null
  training_gate_at_generation: string | null
  override_applied: string | null
  plan_rationale: string
  nutrition_weekly_notes: string | null
}

export interface CheckInRequest {
  user_id: string
  check_in_date: string
  perceived_effort: number | null
  mood: number | null
  free_text: string | null
  override_choice: 'rest_as_recommended' | 'push_through' | null
  override_reason: string | null
}

export interface CheckInResponse {
  saved: boolean
  override_applied: string | null
  plan_updated: boolean
  message: string
}

export interface OverridePrompt {
  show_prompt: boolean
  training_gate: string
  readiness_score: number | null
  narrative: string | null
  already_decided: boolean
  decision: string | null
}

export interface UserProfile {
  user_id: string
  display_name: string | null
  goal_event: string | null
  goal_date: string | null
  fitness_level: string | null
  medical_conditions: string[]
  dietary_preference: string | null
  dietary_allergies: string | null
  max_weekly_hours: number | null
  garmin_email: string | null
  swim_equipment: string | null
  swim_strokes: string | null
  model_analysis: string
  model_planning: string
}

// ── Helper types & functions ──────────────────────────────────────────────

export type GateColor = 'green' | 'yellow' | 'orange' | 'red'

export function gateToColor(gate: string): GateColor {
  const map: Record<string, GateColor> = {
    'PROCEED': 'green',
    'PROCEED_WITH_CAUTION': 'yellow',
    'REST_RECOMMENDED': 'orange',
    'MANDATORY_REST': 'red',
  }
  return map[gate] ?? 'green'
}

export function readinessToColor(score: number): string {
  if (score >= 85) return 'text-green-600'
  if (score >= 70) return 'text-blue-600'
  if (score >= 50) return 'text-yellow-600'
  if (score >= 30) return 'text-orange-600'
  return 'text-red-600'
}

export function sportToEmoji(sport: SportType): string {
  const map: Record<SportType, string> = {
    swim: '🏊', bike: '🚴', run: '🏃', brick: '🚴🏃',
    strength: '💪', yoga: '🧘', active_recovery: '🚶', rest: '😴',
  }
  return map[sport] ?? '🏋️'
}

export function formatDuration(min: number | null): string {
  if (!min) return '—'
  if (min < 60) return `${min}min`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m === 0 ? `${h}h` : `${h}h ${m}min`
}

export function formatDistance(m: number | null): string {
  if (!m) return ''
  if (m >= 1000) return `${(m / 1000).toFixed(1)}km`
  return `${Math.round(m)}m`
}

export function todayStr(): string {
  return new Date().toISOString().split('T')[0]
}

// ── Stats / metrics types ─────────────────────────────────────────────────

export type Trend = 'improving' | 'declining' | 'stable' | 'insufficient_data'

export interface KpiSummary {
  avg_readiness_7d: number | null
  avg_hrv_7d: number | null
  avg_sleep_score_7d: number | null
  avg_acwr_7d: number | null
  total_training_min_7d: number
  total_training_min_14d: number
  trend_readiness: Trend
  trend_hrv: Trend
  trend_sleep: Trend
  best_readiness_14d: number | null
  worst_readiness_14d: number | null
  days_with_data: number
  data_completeness_pct: number
}

export interface WorkoutEntry {
  date: string
  sport: SportType
  duration_min: number | null
  distance_m: number | null
  avg_hr: number | null
}

export interface WeeklyVolume {
  week_start: string
  total_min: number
  by_sport: Record<string, number>
}

export interface KpiMetrics {
  dates: string[]
  readiness_scores: (number | null)[]
  hrv_ms: (number | null)[]
  sleep_scores: (number | null)[]
  body_battery_max: (number | null)[]
  acwr: (number | null)[]
  resting_hr: (number | null)[]
  total_steps: (number | null)[]
  active_calories: (number | null)[]
  summary: KpiSummary
  workouts_14d: WorkoutEntry[]
  weekly_volume: WeeklyVolume[]
}

export interface GoalProgress {
  goal_event: string | null
  goal_date: string | null
  weeks_to_goal: number | null
  days_to_goal: number | null
  phase: string
  phase_description: string
  completion_pct: number
  weekly_volume_target_min: number
  recent_consistency: number
  readiness_trend: string
  on_track: boolean
  coaching_note: string
}

export interface SchedulerStatus {
  is_running: boolean
  jobs: Array<{
    id: string
    next_run: string | null
    trigger: string
  }>
}

// ── Stats helper functions ────────────────────────────────────────────────

export function trendIcon(trend: string): string {
  if (trend === 'improving') return '↑'
  if (trend === 'declining') return '↓'
  if (trend === 'stable') return '→'
  return '—'
}

export function trendColor(trend: string): string {
  if (trend === 'improving') return 'text-green-400'
  if (trend === 'declining') return 'text-red-400'
  return 'text-slate-400'
}

export function phaseColor(phase: string): string {
  const map: Record<string, string> = {
    base:      'bg-blue-900/40 text-blue-300',
    build:     'bg-yellow-900/40 text-yellow-300',
    peak:      'bg-orange-900/40 text-orange-300',
    taper:     'bg-purple-900/40 text-purple-300',
    race_week: 'bg-red-900/40 text-red-300',
    complete:  'bg-green-900/40 text-green-300',
  }
  return map[phase] ?? 'bg-slate-700 text-slate-300'
}

export function formatWeekStart(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function acwrRiskColor(acwr: number | null): string {
  if (acwr === null) return 'text-slate-400'
  if (acwr < 0.8)  return 'text-blue-400'    // undertraining
  if (acwr <= 1.3) return 'text-green-400'   // optimal
  if (acwr <= 1.5) return 'text-orange-400'  // caution
  return 'text-red-400'                      // danger
}
