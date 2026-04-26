<script lang="ts">
  import { onMount } from "svelte";
  import { userId, globalError, isLoading } from "$lib/stores";
  import { getKpiMetrics, getGoalProgress, triggerPipeline } from "$lib/api";
  import type { KpiMetrics, GoalProgress } from "$lib/types";
  import {
    trendIcon,
    trendColor,
    phaseColor,
    formatDuration,
    formatWeekStart,
    acwrRiskColor,
    sportToEmoji,
    formatDistance,
  } from "$lib/types";
  import LineChart from "$lib/components/charts/LineChart.svelte";
  import BarChart from "$lib/components/charts/BarChart.svelte";
  import GaugeWidget from "$lib/components/charts/GaugeWidget.svelte";

  let kpi: KpiMetrics | null = $state(null);
  let goal: GoalProgress | null = $state(null);
  let loading = $state(true);
  let selectedDays = $state(14);

  async function reload() {
    if (!$userId) return;
    loading = true;
    kpi = await getKpiMetrics($userId, selectedDays);
    loading = false;
  }

  onMount(async () => {
    if (!$userId) {
      loading = false;
      return;
    }
    try {
      [kpi, goal] = await Promise.all([
        getKpiMetrics($userId, selectedDays),
        getGoalProgress($userId),
      ]);
    } catch (e) {
      $globalError = "Failed to load stats";
    } finally {
      loading = false;
    }
  });

  let prevDays = $state(14);

  $effect(() => {
    const days = selectedDays;
    if ($userId && days !== prevDays) {
      prevDays = days;
      reload();
    }
  });

  // ── Derived chart data ────────────────────────────────────────────────

  function readinessColor(v: number | null): string {
    if (!v) return "#94a3b8";
    if (v >= 85) return "#22c55e";
    if (v >= 70) return "#3b82f6";
    if (v >= 50) return "#f97316";
    return "#ef4444";
  }

  function scoreColor(v: number | null): string {
    if (!v) return "#94a3b8";
    if (v >= 80) return "#22c55e";
    if (v >= 65) return "#3b82f6";
    if (v >= 50) return "#f97316";
    return "#ef4444";
  }

  function acwrLabel(v: number | null): string {
    if (v === null) return "—";
    if (v < 0.8) return "UNDER";
    if (v <= 1.3) return "OPTIMAL";
    if (v <= 1.5) return "CAUTION";
    return "DANGER";
  }

  function acwrBgColor(v: number | null): string {
    if (v === null) return "#334155";
    if (v < 0.8) return "#1e40af";
    if (v <= 1.3) return "#166534";
    if (v <= 1.5) return "#9a3412";
    return "#7f1d1d";
  }

  const SPORT_COLORS: Record<string, string> = {
    run: "#ef4444",
    bike: "#3b82f6",
    swim: "#06b6d4",
    strength: "#8b5cf6",
    brick: "#f97316",
    yoga: "#ec4899",
    active_recovery: "#94a3b8",
    rest: "#e2e8f0",
  };

  const volumeLabels = $derived.by((): string[] => {
    if (!kpi) return [];
    return kpi.weekly_volume.map((w) => formatWeekStart(w.week_start));
  });
  const volumeSports = $derived.by((): string[] => {
    if (!kpi) return [];
    return [
      ...new Set(kpi.weekly_volume.flatMap((w) => Object.keys(w.by_sport))),
    ];
  });
  const volumeDatasets = $derived.by(() => {
    if (!kpi) return [];
    const k = kpi;
    return volumeSports.map((sport: string) => ({
      label: sport,
      data: k.weekly_volume.map((w) => w.by_sport[sport] ?? 0),
      color: SPORT_COLORS[sport] ?? "#94a3b8",
    }));
  });

  const acwrFill = $derived.by(() => {
    if (!kpi) return [];
    return kpi.acwr.map((v) => (v !== null ? v * 50 : null));
  });

  const acwr = $derived.by((): number | null => {
    if (!kpi) return null;
    return kpi.summary.avg_acwr_7d;
  });

  async function runPipeline() {
    if (!$userId) return;
    await triggerPipeline($userId);
    await reload();
  }
</script>

<div class="max-w-7xl mx-auto px-4 py-6 space-y-6">
  <!-- ROW 0: Header -->
  <div class="flex items-center justify-between">
    <h1 class="text-2xl font-bold text-slate-100">Performance Dashboard</h1>
    <div class="flex gap-2">
      {#each [7, 14, 28] as d}
        <button
          onclick={() => {
            selectedDays = d;
          }}
          class={`px-3 py-1 rounded-lg text-sm font-medium transition-colors ${
            selectedDays === d
              ? "bg-blue-600 text-white"
              : "bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700"
          }`}>{d}d</button
        >
      {/each}
    </div>
  </div>

  {#if loading}
    <!-- Skeleton loaders -->
    <div class="animate-pulse space-y-6">
      <div class="h-32 bg-slate-800 rounded-xl"></div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        {#each [0, 1, 2, 3] as _}
          <div class="h-48 bg-slate-800 rounded-xl"></div>
        {/each}
      </div>
      <div class="grid md:grid-cols-2 gap-4">
        <div class="h-64 bg-slate-800 rounded-xl"></div>
        <div class="h-64 bg-slate-800 rounded-xl"></div>
      </div>
      <div class="grid md:grid-cols-2 gap-4">
        <div class="h-56 bg-slate-800 rounded-xl"></div>
        <div class="h-56 bg-slate-800 rounded-xl"></div>
      </div>
      <div class="h-64 bg-slate-800 rounded-xl"></div>
      <div class="grid md:grid-cols-2 gap-4">
        <div class="h-56 bg-slate-800 rounded-xl"></div>
        <div class="h-56 bg-slate-800 rounded-xl"></div>
      </div>
      <div class="h-56 bg-slate-800 rounded-xl"></div>
    </div>
  {:else if !kpi}
    <!-- Error / empty state -->
    <div
      class="flex flex-col items-center justify-center py-24 text-center space-y-4"
    >
      <p class="text-3xl">📊</p>
      <p class="text-slate-300 text-lg">No data available.</p>
      <p class="text-slate-500 text-sm">
        Run the pipeline to generate your first report.
      </p>
      <button
        onclick={runPipeline}
        class="mt-4 px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
        >Run Pipeline</button
      >
    </div>
  {:else}
    <!-- ROW 1: Goal Progress Card -->
    {#if goal}
      {@const phaseCls = phaseColor(goal.phase)}
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-5 border-l-4"
        style="border-left-color: {goal.on_track ? '#22c55e' : '#f59e0b'}"
      >
        {#if goal.goal_event}
          <div class="grid md:grid-cols-3 gap-6 items-center">
            <!-- Col 1: Goal info -->
            <div class="space-y-2">
              <span
                class="inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase {phaseCls}"
              >
                {goal.phase.replace("_", " ")} PHASE
              </span>
              <p class="text-xl font-bold text-slate-100">{goal.goal_event}</p>
              {#if goal.goal_date}
                <p class="text-sm text-slate-400">
                  {goal.goal_date} · {goal.weeks_to_goal} weeks away
                </p>
              {/if}
              <p class="text-sm text-slate-400 italic">{goal.coaching_note}</p>
            </div>
            <!-- Col 2: Gauge -->
            <div class="flex justify-center">
              <GaugeWidget
                value={goal.completion_pct}
                label="Complete"
                sublabel="{goal.completion_pct.toFixed(0)}%"
                color="#3b82f6"
                size={140}
              />
            </div>
            <!-- Col 3: Stats -->
            <div class="space-y-3">
              <div>
                <div class="flex justify-between text-sm mb-1">
                  <span class="text-slate-400">Consistency</span>
                  <span
                    class="font-semibold {goal.recent_consistency >= 80
                      ? 'text-green-400'
                      : goal.recent_consistency >= 60
                        ? 'text-yellow-400'
                        : 'text-red-400'}">{goal.recent_consistency}%</span
                  >
                </div>
                <div class="w-full bg-slate-700 rounded-full h-2">
                  <div
                    class="h-2 rounded-full transition-all {goal.recent_consistency >=
                    80
                      ? 'bg-green-500'
                      : goal.recent_consistency >= 60
                        ? 'bg-yellow-500'
                        : 'bg-red-500'}"
                    style="width: {goal.recent_consistency}%"
                  ></div>
                </div>
              </div>
              <p class="text-sm text-slate-400">
                🎯 {goal.weekly_volume_target_min}min/week target
              </p>
              <p
                class="text-sm {goal.on_track
                  ? 'text-green-400'
                  : 'text-yellow-400'}"
              >
                {goal.on_track ? "✅ On track" : "⚠️ Behind schedule"}
              </p>
            </div>
          </div>
        {:else}
          <div class="text-center py-6 space-y-3">
            <p class="text-slate-400">
              Set your goal in Settings to see progress tracking.
            </p>
            <a
              href="/settings"
              class="inline-block px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
              >Go to Settings</a
            >
          </div>
        {/if}
      </div>
    {/if}

    <!-- ROW 2: 4 KPI Gauges -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <!-- Readiness gauge -->
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col items-center gap-2"
      >
        <GaugeWidget
          value={kpi.summary.avg_readiness_7d ?? 0}
          label="Readiness (7d)"
          sublabel={kpi.summary.avg_readiness_7d
            ? kpi.summary.avg_readiness_7d.toFixed(0)
            : "—"}
          color={readinessColor(kpi.summary.avg_readiness_7d)}
          size={120}
        />
        <p class="text-xs {trendColor(kpi.summary.trend_readiness)}">
          {trendIcon(kpi.summary.trend_readiness)} vs prior week
        </p>
      </div>

      <!-- HRV gauge -->
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col items-center gap-2"
      >
        <GaugeWidget
          value={Math.min(100, ((kpi.summary.avg_hrv_7d ?? 0) / 80) * 100)}
          label="HRV 7d avg"
          sublabel="{kpi.summary.avg_hrv_7d?.toFixed(0) ?? '—'}ms"
          color="#8b5cf6"
          size={120}
        />
        <p class="text-xs {trendColor(kpi.summary.trend_hrv)}">
          {trendIcon(kpi.summary.trend_hrv)} vs prior week
        </p>
      </div>

      <!-- Sleep gauge -->
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col items-center gap-2"
      >
        <GaugeWidget
          value={kpi.summary.avg_sleep_score_7d ?? 0}
          label="Sleep Score"
          sublabel={kpi.summary.avg_sleep_score_7d
            ? kpi.summary.avg_sleep_score_7d.toFixed(0)
            : "—"}
          color={scoreColor(kpi.summary.avg_sleep_score_7d)}
          size={120}
        />
        <p class="text-xs {trendColor(kpi.summary.trend_sleep)}">
          {trendIcon(kpi.summary.trend_sleep)} vs prior week
        </p>
      </div>

      <!-- ACWR card (not a gauge) -->
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col items-center justify-center gap-2"
        style="background-color: {acwrBgColor(acwr)}22"
      >
        <p class="text-4xl font-bold {acwrRiskColor(acwr)}">
          {acwr?.toFixed(2) ?? "—"}
        </p>
        <p
          class="text-sm font-semibold {acwrRiskColor(
            acwr,
          )} uppercase tracking-wide"
        >
          {acwrLabel(acwr)}
        </p>
        <p class="text-xs text-slate-500 text-center">
          Acute:Chronic Workload Ratio
        </p>
        <!-- Mini ACWR scale bar -->
        <div class="w-full mt-1">
          <div class="relative h-2 bg-slate-700 rounded-full">
            <div class="absolute inset-0 flex">
              <div class="flex-1 bg-blue-900 rounded-l-full opacity-60"></div>
              <!-- 0–0.8 -->
              <div class="flex-1 bg-green-700 opacity-60"></div>
              <!-- 0.8–1.3 -->
              <div class="w-8 bg-orange-700 opacity-60"></div>
              <!-- 1.3–1.5 -->
              <div class="w-4 bg-red-700 rounded-r-full opacity-60"></div>
              <!-- 1.5–2.0 -->
            </div>
            {#if acwr !== null}
              <div
                class="absolute top-1/2 -translate-y-1/2 w-2 h-3 rounded-sm {acwrRiskColor(
                  acwr,
                ).replace('text-', 'bg-')}"
                style="left: {Math.min(98, Math.max(1, (acwr / 2.0) * 100))}%"
              ></div>
            {/if}
          </div>
          <div class="flex justify-between text-xs text-slate-600 mt-0.5">
            <span>0</span><span>0.8</span><span>1.3</span><span>2.0</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ROW 3: Readiness + HRV trends -->
    <div class="grid md:grid-cols-2 gap-4">
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3"
      >
        <div class="flex items-center gap-2">
          <h2 class="font-semibold text-slate-200">Readiness Score</h2>
          <span class="text-sm {trendColor(kpi.summary.trend_readiness)}">
            {trendIcon(kpi.summary.trend_readiness)}
            {kpi.summary.trend_readiness}
          </span>
        </div>
        <LineChart
          labels={kpi.dates}
          datasets={[
            {
              label: "Readiness",
              data: kpi.readiness_scores,
              color: "#3b82f6",
              dashed: false,
            },
          ]}
          height={200}
          yMin={0}
          yMax={100}
          fillArea={true}
        />
      </div>
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3"
      >
        <div class="flex items-center gap-2">
          <h2 class="font-semibold text-slate-200">HRV (ms)</h2>
          <span class="text-sm {trendColor(kpi.summary.trend_hrv)}">
            {trendIcon(kpi.summary.trend_hrv)}
          </span>
        </div>
        <LineChart
          labels={kpi.dates}
          datasets={[
            { label: "HRV", data: kpi.hrv_ms, color: "#8b5cf6", dashed: false },
            {
              label: "Baseline",
              data: Array(kpi.dates.length).fill(kpi.summary.avg_hrv_7d),
              color: "#8b5cf6",
              dashed: true,
            },
          ]}
          unit="ms"
          height={200}
        />
      </div>
    </div>

    <!-- ROW 4: Sleep + Body Battery -->
    <div class="grid md:grid-cols-2 gap-4">
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3"
      >
        <div class="flex items-center justify-between">
          <h2 class="font-semibold text-slate-200">Sleep Quality</h2>
          <span class="text-sm {trendColor(kpi.summary.trend_sleep)}">
            {trendIcon(kpi.summary.trend_sleep)}
            {kpi.summary.trend_sleep}
          </span>
        </div>
        <LineChart
          labels={kpi.dates}
          datasets={[
            {
              label: "Sleep Score",
              data: kpi.sleep_scores,
              color: "#6366f1",
              dashed: false,
            },
          ]}
          height={180}
          yMin={0}
          yMax={100}
        />
        <div class="flex gap-3 flex-wrap">
          <span class="text-xs bg-slate-700 text-slate-300 px-2 py-1 rounded">
            Avg: {kpi.summary.avg_sleep_score_7d?.toFixed(0) ?? "—"}
          </span>
          <span
            class="text-xs bg-slate-700 text-slate-300 px-2 py-1 rounded {trendColor(
              kpi.summary.trend_sleep,
            )}"
          >
            Trend: {trendIcon(kpi.summary.trend_sleep)}
            {kpi.summary.trend_sleep}
          </span>
        </div>
      </div>
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3"
      >
        <h2 class="font-semibold text-slate-200">Body Battery</h2>
        <LineChart
          labels={kpi.dates}
          datasets={[
            {
              label: "Max",
              data: kpi.body_battery_max,
              color: "#22c55e",
              dashed: false,
            },
          ]}
          height={180}
          yMin={0}
          yMax={100}
          fillArea={true}
        />
      </div>
    </div>

    <!-- ROW 5: Weekly Training Volume -->
    <div class="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
      <div class="flex items-center justify-between flex-wrap gap-2">
        <h2 class="font-semibold text-slate-200">Weekly Training Volume</h2>
        <div class="flex flex-wrap gap-2">
          {#each volumeSports as sport}
            <span class="flex items-center gap-1 text-xs text-slate-300">
              <span
                class="inline-block w-3 h-3 rounded-sm"
                style="background:{SPORT_COLORS[sport] ?? '#94a3b8'}"
              ></span>
              {sport}
            </span>
          {/each}
        </div>
      </div>
      {#if volumeLabels.length > 0}
        <BarChart
          labels={volumeLabels}
          datasets={volumeDatasets}
          stacked={true}
          height={200}
          unit="min"
        />
      {:else}
        <p class="text-slate-500 text-sm text-center py-8">
          No weekly volume data available.
        </p>
      {/if}
      <div class="flex gap-4 text-sm text-slate-400 flex-wrap">
        <span
          >Last 7d: <strong class="text-slate-200"
            >{formatDuration(kpi.summary.total_training_min_7d)}</strong
          ></span
        >
        <span
          >Last 14d: <strong class="text-slate-200"
            >{formatDuration(kpi.summary.total_training_min_14d)}</strong
          ></span
        >
      </div>
    </div>

    <!-- ROW 6: ACWR + Resting HR -->
    <div class="grid md:grid-cols-2 gap-4">
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-2"
      >
        <h2 class="font-semibold text-slate-200">
          Acute:Chronic Workload Ratio
        </h2>
        <p class="text-xs text-slate-500">
          Stay between 0.8 and 1.3 for optimal adaptation
        </p>
        <LineChart
          labels={kpi.dates}
          datasets={[
            { label: "ACWR", data: kpi.acwr, color: "#f59e0b", dashed: false },
            {
              label: "Upper limit (1.3)",
              data: Array(kpi.dates.length).fill(1.3),
              color: "#ef4444",
              dashed: true,
            },
            {
              label: "Lower limit (0.8)",
              data: Array(kpi.dates.length).fill(0.8),
              color: "#3b82f6",
              dashed: true,
            },
          ]}
          height={180}
          yMin={0}
          yMax={2.0}
        />
      </div>
      <div
        class="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-2"
      >
        <h2 class="font-semibold text-slate-200">Resting Heart Rate</h2>
        <p class="text-xs text-slate-500">
          Lower = better cardiovascular fitness
        </p>
        <LineChart
          labels={kpi.dates}
          datasets={[
            {
              label: "Resting HR",
              data: kpi.resting_hr,
              color: "#f43f5e",
              dashed: false,
            },
          ]}
          unit=" bpm"
          height={180}
        />
      </div>
    </div>

    <!-- ROW 7: Recent Workouts Table -->
    <div class="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
      <h2 class="font-semibold text-slate-200">Recent Workouts (14d)</h2>
      {#if kpi.workouts_14d.length === 0}
        <p class="text-slate-500 text-sm text-center py-8">
          No workouts recorded in the last 14 days.
        </p>
      {:else}
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-slate-500 border-b border-slate-700 text-left">
                <th class="pb-2 pr-4 font-medium">Date</th>
                <th class="pb-2 pr-4 font-medium">Sport</th>
                <th class="pb-2 pr-4 font-medium">Duration</th>
                <th class="pb-2 pr-4 font-medium">Distance</th>
                <th class="pb-2 font-medium">Avg HR</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-700/50">
              {#each kpi.workouts_14d as w}
                <tr
                  class="text-slate-300 hover:bg-slate-700/30 transition-colors"
                >
                  <td class="py-2 pr-4 text-slate-400 whitespace-nowrap"
                    >{w.date}</td
                  >
                  <td class="py-2 pr-4 whitespace-nowrap"
                    >{sportToEmoji(w.sport)} {w.sport}</td
                  >
                  <td class="py-2 pr-4">{formatDuration(w.duration_min)}</td>
                  <td class="py-2 pr-4"
                    >{formatDistance(w.distance_m) || "—"}</td
                  >
                  <td class="py-2">{w.avg_hr ? `${w.avg_hr} bpm` : "—"}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  {/if}
</div>
