<script lang="ts">
  import {
    currentPlan,
    todayReport,
    todaySession,
    tomorrowSession,
    overridePrompt,
    pipelineRunning,
    addToast,
    userId,
    showOverrideModal,
    isLoading,
  } from "$lib/stores";
  import {
    sportToEmoji,
    formatDuration,
    formatDistance,
    gateToColor,
    readinessToColor,
    todayStr,
  } from "$lib/types";
  import type { TrainingSession } from "$lib/types";
  import {
    ChevronRight,
    AlertTriangle,
    CheckCircle,
    Clock,
    Zap,
    TrendingUp,
    Calendar,
  } from "lucide-svelte";
  import {
    runFullPipeline,
    getCurrentPlan,
    getReadinessReport,
    submitCheckIn,
    triggerSync,
    getKpiMetrics,
  } from "$lib/api";
  import OverrideModal from "$lib/components/OverrideModal.svelte";
  import { onMount } from "svelte";

  // ── Getting-started state ──────────────────────────────────────
  let hasSyncData = $state(false);
  let syncStarted = $state(false);
  let syncLoading = $state(false);

  onMount(async () => {
    if (!$userId) return;
    try {
      const kpi = await getKpiMetrics($userId, 1);
      hasSyncData =
        (kpi.summary?.days_with_data ?? 0) > 0 ||
        (kpi.workouts_14d?.length ?? 0) > 0;
    } catch {
      // no data yet — keep false
    }
  });

  async function handleGettingStartedSync() {
    if (!$userId) return;
    syncLoading = true;
    try {
      await triggerSync($userId);
      syncStarted = true;
      hasSyncData = true; // optimistic
      addToast("Sync started — takes ~60 seconds", "info");
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : "Sync failed", "error");
    } finally {
      syncLoading = false;
    }
  }

  // ── Zone classes ──────────────────────────────────────────────────────
  const ZONE_CLASS: Record<string, string> = {
    Z1: "zone-z1",
    Z2: "zone-z2",
    Z3: "zone-z3",
    Z4: "zone-z4",
    Z5: "zone-z5",
  };

  // ── Gate display ──────────────────────────────────────────────────────
  const GATE_LABEL: Record<string, string> = {
    PROCEED: "Proceed ✓",
    PROCEED_WITH_CAUTION: "Caution ⚠",
    REST_RECOMMENDED: "Rest Rec. 🔴",
    MANDATORY_REST: "Mandatory Rest 🛑",
  };
  const GATE_PILL: Record<string, string> = {
    green: "bg-green-100 text-green-700",
    yellow: "bg-yellow-100 text-yellow-700",
    orange: "bg-orange-100 text-orange-700",
    red: "bg-red-100 text-red-700",
  };

  // ── Expanded session accordion ────────────────────────────────────────
  let expandedDates = $state(new Set<string>());
  function toggleSession(date: string) {
    const next = new Set(expandedDates);
    if (next.has(date)) next.delete(date);
    else next.add(date);
    expandedDates = next;
  }

  // ── "Show more" for hero description ─────────────────────────────────
  let heroExpanded = $state(false);

  // ── Override handling ─────────────────────────────────────────────────
  async function handleRest() {
    const uid = $userId;
    if (!uid) return;
    showOverrideModal.set(false);
    isLoading.set(true);
    try {
      await submitCheckIn({
        user_id: uid,
        check_in_date: todayStr(),
        perceived_effort: null,
        mood: null,
        free_text: null,
        override_choice: "rest_as_recommended",
        override_reason: null,
      });
      overridePrompt.update((p) =>
        p
          ? { ...p, already_decided: true, decision: "rest_as_recommended" }
          : p,
      );
      const updated = await getCurrentPlan(uid);
      currentPlan.set(updated);
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : "Override failed", "error");
    } finally {
      isLoading.set(false);
    }
  }

  async function handlePush() {
    const uid = $userId;
    if (!uid) return;
    showOverrideModal.set(false);
    isLoading.set(true);
    try {
      await submitCheckIn({
        user_id: uid,
        check_in_date: todayStr(),
        perceived_effort: null,
        mood: null,
        free_text: null,
        override_choice: "push_through",
        override_reason: null,
      });
      overridePrompt.update((p) =>
        p ? { ...p, already_decided: true, decision: "push_through" } : p,
      );
      const updated = await getCurrentPlan(uid);
      currentPlan.set(updated);
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : "Override failed", "error");
    } finally {
      isLoading.set(false);
    }
  }

  // ── Pipeline trigger ──────────────────────────────────────────────────
  async function handleRunPipeline() {
    if (!$userId || $pipelineRunning) return;
    pipelineRunning.set(true);
    try {
      const result = await runFullPipeline($userId);
      if (!result.success) {
        addToast(result.error ?? "Pipeline failed", "error");
        return;
      }
      const [plan, report] = await Promise.all([
        getCurrentPlan($userId),
        getReadinessReport($userId),
      ]);
      currentPlan.set(plan);
      todayReport.set(report);
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : "Pipeline failed", "error");
    } finally {
      pipelineRunning.set(false);
    }
  }

  // ── Date helpers ──────────────────────────────────────────────────────
  const today = todayStr();

  function fmtHeader(dateStr: string): string {
    const d = new Date(dateStr + "T00:00:00");
    return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric" });
  }

  function timeAgo(iso: string | null | undefined): string {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  }

  // ── Split sessions into weeks ─────────────────────────────────────────
  let week1 = $derived($currentPlan?.sessions.slice(0, 7) ?? []);
  let week2 = $derived($currentPlan?.sessions.slice(7) ?? []);
  let w1Theme = $derived(
    $currentPlan?.weekly_targets?.[0]?.weekly_theme ?? null,
  );
  let w2Theme = $derived(
    $currentPlan?.weekly_targets?.[1]?.weekly_theme ?? null,
  );
</script>

<div class="max-w-6xl mx-auto px-4 py-6 space-y-6 animate-fade-in">
  <!-- ════════════════════════════════════════════════════════════════ -->
  <!-- GETTING STARTED empty state (no plan and no readiness data)      -->
  <!-- ════════════════════════════════════════════════════════════════ -->
  {#if !$currentPlan && !$todayReport && !$isLoading}
    <div class="max-w-lg mx-auto card p-8 space-y-6">
      <!-- Icon + title -->
      <div class="text-center space-y-2">
        <div class="text-6xl">⚡</div>
        <h2 class="text-xl font-bold text-slate-100">No data yet</h2>
        <p class="text-sm text-slate-400">
          Follow these steps to get your AI coach running:
        </p>
      </div>

      <!-- Step list -->
      <ol class="relative space-y-0">
        <!-- Step 1 -->
        <li class="flex gap-4 pb-8 relative">
          <!-- Connector line -->
          <div class="flex flex-col items-center">
            <div
              class="w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10
                        {hasSyncData
                ? 'bg-green-600 text-white'
                : 'bg-blue-600 text-white'} text-xs font-bold"
            >
              {#if hasSyncData}
                ✓
              {:else}
                1
              {/if}
            </div>
            <div class="w-px flex-1 bg-slate-700 mt-1"></div>
          </div>
          <div class="flex-1 pt-0.5 space-y-2">
            <p class="text-sm font-semibold text-slate-100">
              Sync your Garmin data
            </p>
            <p class="text-xs text-slate-400">
              Pull the last 30 days of wearable data from Garmin Connect.
            </p>
            {#if !hasSyncData}
              <button
                onclick={handleGettingStartedSync}
                disabled={syncLoading || syncStarted}
                class="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700
                       text-white rounded-lg transition disabled:opacity-60"
              >
                {#if syncLoading}
                  <span
                    class="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin"
                  ></span>
                  Syncing…
                {:else if syncStarted}
                  ⏳ Sync running…
                {:else}
                  🔄 Sync Garmin Data
                {/if}
              </button>
            {:else}
              <span
                class="inline-flex items-center gap-1.5 text-xs text-green-400"
              >
                <CheckCircle size={13} /> Garmin data synced
              </span>
            {/if}
          </div>
        </li>

        <!-- Step 2 -->
        <li class="flex gap-4 pb-8 relative">
          <div class="flex flex-col items-center">
            <div
              class="w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10
                        {!hasSyncData
                ? 'bg-slate-700 text-slate-500'
                : 'bg-blue-600 text-white'} text-xs font-bold"
            >
              2
            </div>
            <div class="w-px flex-1 bg-slate-700 mt-1"></div>
          </div>
          <div class="flex-1 pt-0.5 space-y-2">
            <p
              class="text-sm font-semibold {hasSyncData
                ? 'text-slate-100'
                : 'text-slate-500'}"
            >
              Generate your first plan
            </p>
            <p class="text-xs text-slate-400">
              Run the AI analysis and get your personalised training plan.
            </p>
            <button
              onclick={handleRunPipeline}
              disabled={!hasSyncData || $pipelineRunning}
              class="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700
                     text-white rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {#if $pipelineRunning}
                <span
                  class="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin"
                ></span>
                Generating…
              {:else}
                <Zap size={14} /> Generate My Plan
              {/if}
            </button>
          </div>
        </li>

        <!-- Step 3 -->
        <li class="flex gap-4">
          <div class="flex flex-col items-center">
            <div
              class="w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10
                        bg-slate-700 text-slate-400 text-xs font-bold"
            >
              3
            </div>
          </div>
          <div class="flex-1 pt-0.5 space-y-2">
            <p class="text-sm font-semibold text-slate-400">
              Complete your profile
            </p>
            <p class="text-xs text-slate-400">
              Set your goal event and date for personalised coaching.
            </p>
            <a
              href="/settings"
              class="inline-flex items-center gap-1.5 px-4 py-2 text-sm border border-slate-600
                     text-slate-300 hover:bg-slate-700 rounded-lg transition"
            >
              <ChevronRight size={14} /> Go to Settings
            </a>
          </div>
        </li>
      </ol>

      <p class="text-xs text-slate-500 text-center leading-relaxed">
        First run takes 2–3 minutes.<br />
        After setup, your plan updates automatically every morning.
      </p>
    </div>
  {:else}
    {#if $overridePrompt?.show_prompt && !$overridePrompt?.already_decided}
      <div
        class="card border-2 border-amber-400 animate-pulse-border p-5 space-y-3"
      >
        <div class="flex items-start gap-3">
          <AlertTriangle class="text-amber-500 mt-0.5 shrink-0" size={22} />
          <div class="flex-1">
            <p class="font-semibold text-slate-100 text-base">
              Your body recommends rest today
            </p>
            {#if $overridePrompt.narrative}
              <p class="text-slate-400 text-sm mt-1 line-clamp-2">
                {$overridePrompt.narrative}
              </p>
            {/if}
          </div>
          <span
            class="badge {GATE_PILL[
              gateToColor($overridePrompt.training_gate ?? '')
            ]}"
          >
            {$overridePrompt.training_gate?.replace(/_/g, " ")}
          </span>
        </div>
        <div class="flex gap-3 pt-1">
          <button
            onclick={() => showOverrideModal.set(true)}
            class="flex-1 btn-primary bg-green-500 hover:bg-green-600 flex items-center justify-center gap-2"
          >
            <CheckCircle size={16} /> Rest as Recommended
          </button>
          <button
            onclick={() => showOverrideModal.set(true)}
            class="flex-1 border border-red-500/70 text-red-400 rounded-lg px-4 py-2 text-sm
                 font-medium hover:bg-red-900/30 transition flex items-center justify-center gap-2"
          >
            <Zap size={16} /> Push Through
          </button>
        </div>
      </div>
    {:else if $overridePrompt?.already_decided}
      <div
        class="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-slate-700/50 text-sm text-slate-400"
      >
        <CheckCircle size={15} class="text-green-500" />
        Override recorded:
        <span class="font-medium text-slate-300">
          {$overridePrompt.decision?.replace(/_/g, " ")}
        </span>
      </div>
    {/if}

    <!-- ════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 1: Today's Hero Card                                     -->
    <!-- ════════════════════════════════════════════════════════════════ -->
    {#if $todaySession}
      {@const s = $todaySession}
      <div class="card p-0 overflow-hidden">
        <!-- Banners -->
        {#if s.override_applied}
          <div
            class="bg-amber-900/30 border-b border-amber-700/50 px-5 py-2 flex items-center gap-2 text-sm text-amber-400"
          >
            <AlertTriangle size={14} />
            <span>Modified — push-through override applied</span>
          </div>
        {/if}
        {#if s.readiness_adjusted}
          <div
            class="bg-blue-900/30 border-b border-blue-700/50 px-5 py-2 flex items-center gap-2 text-sm text-blue-400"
          >
            <TrendingUp size={14} /> <span>Adjusted for today's readiness</span>
          </div>
        {/if}

        <!-- Main hero content -->
        <div class="p-5 sm:p-6">
          <div class="flex items-start gap-4">
            <!-- Sport emoji -->
            <div
              class="text-5xl leading-none shrink-0 mt-1"
              role="img"
              aria-label={s.sport}
            >
              {sportToEmoji(s.sport)}
            </div>

            <!-- Title block -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-0.5">
                <span
                  class="text-xs font-medium text-slate-400 uppercase tracking-wide"
                >
                  {s.sport.replace(/_/g, " ")} · {new Date(
                    today + "T00:00:00",
                  ).toLocaleDateString("en-GB", {
                    weekday: "long",
                    day: "numeric",
                    month: "short",
                  })}
                </span>
              </div>
              <h2 class="text-xl font-bold text-slate-100 leading-snug">
                {s.title}
              </h2>
              <p class="text-sm text-slate-400 italic mt-0.5">{s.key_focus}</p>
            </div>

            <!-- Badges -->
            <div class="flex flex-col items-end gap-1.5 shrink-0">
              {#if s.duration_min}
                <span class="badge bg-slate-700 text-slate-300 gap-1">
                  <Clock size={11} />{formatDuration(s.duration_min)}
                </span>
              {/if}
              {#if s.intensity_zone}
                <span
                  class="badge {ZONE_CLASS[s.intensity_zone] ??
                    'bg-slate-700 text-slate-300'}"
                >
                  {s.intensity_zone}
                </span>
              {/if}
              {#if s.distance_m}
                <span class="badge bg-slate-700 text-slate-300"
                  >{formatDistance(s.distance_m)}</span
                >
              {/if}
            </div>
          </div>

          <!-- Description -->
          <div class="mt-4 text-sm text-slate-300 leading-relaxed">
            <p class={heroExpanded ? "" : "line-clamp-3"}>{s.description}</p>
            {#if s.description.length > 180}
              <button
                onclick={() => (heroExpanded = !heroExpanded)}
                class="text-blue-500 hover:text-blue-700 text-xs mt-1 font-medium transition"
              >
                {heroExpanded ? "Show less ↑" : "Show more ↓"}
              </button>
            {/if}
          </div>

          <!-- Exercises table -->
          {#if s.exercises && s.exercises.length > 0}
            <div class="mt-4 pt-4 border-t border-slate-700 space-y-2">
              <p
                class="text-xs font-semibold text-slate-400 uppercase tracking-wide"
              >
                Exercises
              </p>
              <div class="overflow-x-auto">
                <table class="w-full text-xs">
                  <thead>
                    <tr class="text-left text-slate-500">
                      <th class="pb-1.5 pr-3 font-medium">Exercise</th>
                      <th class="pb-1.5 pr-3 font-medium w-10">Sets</th>
                      <th class="pb-1.5 pr-3 font-medium w-20">Reps / Time</th>
                      <th class="pb-1.5 font-medium">Notes</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-700/60">
                    {#each s.exercises as ex}
                      <tr class="align-top">
                        <td class="py-1.5 pr-3 font-medium text-slate-200"
                          >{ex.exercise}</td
                        >
                        <td class="py-1.5 pr-3 text-slate-400">{ex.sets}</td>
                        <td class="py-1.5 pr-3 text-slate-400"
                          >{ex.reps_or_duration}</td
                        >
                        <td class="py-1.5 text-slate-500">{ex.notes ?? "—"}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            </div>
          {/if}

          <!-- Swim sets -->
          {#if s.swim_sets && s.swim_sets.length > 0}
            <div class="mt-4 pt-4 border-t border-slate-700 space-y-2">
              <p
                class="text-xs font-semibold text-slate-400 uppercase tracking-wide"
              >
                Swim Sets
              </p>
              <div class="overflow-x-auto">
                <table class="w-full text-xs">
                  <thead>
                    <tr class="text-left text-slate-500">
                      <th class="pb-1.5 pr-3 font-medium">Stroke</th>
                      <th class="pb-1.5 pr-3 font-medium">Volume</th>
                      <th class="pb-1.5 pr-3 font-medium w-14">Rest</th>
                      <th class="pb-1.5 pr-3 font-medium w-14">Zone</th>
                      <th class="pb-1.5 font-medium">Notes</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-700/60">
                    {#each s.swim_sets as set}
                      <tr class="align-top">
                        <td
                          class="py-1.5 pr-3 font-medium text-slate-200 capitalize"
                          >{set.stroke}</td
                        >
                        <td class="py-1.5 pr-3 text-slate-400"
                          >{set.reps} × {set.distance_m}m</td
                        >
                        <td class="py-1.5 pr-3 text-slate-400"
                          >{set.rest_sec != null ? set.rest_sec + "s" : "—"}</td
                        >
                        <td class="py-1.5 pr-3 text-slate-400"
                          >{set.intensity ?? "—"}</td
                        >
                        <td class="py-1.5 text-slate-500">{set.notes ?? "—"}</td
                        >
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            </div>
          {/if}

          <!-- Nutrition strip -->
          {#if s.nutrition}
            <div
              class="mt-4 pt-4 border-t border-slate-700 grid grid-cols-1 sm:grid-cols-3 gap-3"
            >
              {#if s.nutrition.pre_session}
                <div class="text-xs">
                  <p
                    class="font-semibold text-slate-400 uppercase tracking-wide mb-0.5"
                  >
                    Pre
                  </p>
                  <p class="text-slate-300">{s.nutrition.pre_session}</p>
                </div>
              {/if}
              {#if s.nutrition.during_session}
                <div class="text-xs">
                  <p
                    class="font-semibold text-slate-400 uppercase tracking-wide mb-0.5"
                  >
                    During
                  </p>
                  <p class="text-slate-300">{s.nutrition.during_session}</p>
                </div>
              {/if}
              {#if s.nutrition.post_session}
                <div class="text-xs">
                  <p
                    class="font-semibold text-slate-400 uppercase tracking-wide mb-0.5"
                  >
                    Post
                  </p>
                  <p class="text-slate-300">{s.nutrition.post_session}</p>
                </div>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    {:else if !$currentPlan}
      <div class="card p-10 text-center space-y-4">
        <div class="text-5xl">🏋️</div>
        <p class="text-slate-300 font-medium">No plan loaded yet.</p>
        <p class="text-slate-400 text-sm">
          Run the pipeline to generate your personalised training plan.
        </p>
        <button
          onclick={handleRunPipeline}
          disabled={$pipelineRunning}
          class="btn-primary mx-auto flex items-center gap-2 disabled:opacity-60"
        >
          {#if $pipelineRunning}
            <span
              class="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin"
            ></span>
            Running…
          {:else}
            <Zap size={16} /> Run Pipeline
          {/if}
        </button>
      </div>
    {:else}
      <div class="card p-6 text-center text-slate-400 text-sm">
        No session scheduled for today — enjoy the rest day! 😴
      </div>
    {/if}

    <!-- ════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 2: Readiness Banner                                      -->
    <!-- ════════════════════════════════════════════════════════════════ -->
    {#if $todayReport}
      {@const r = $todayReport}
      {@const gColor = gateToColor(r.training_gate)}
      <div class="card px-5 py-3.5 flex flex-wrap gap-3 items-center">
        <!-- Score -->
        <div class="flex items-center gap-2 mr-1">
          <TrendingUp size={15} class="text-slate-400" />
          <span class="text-xs text-slate-400 font-medium">Readiness</span>
          <span
            class="font-bold text-base {readinessToColor(r.readiness_score)}"
            >{r.readiness_score}</span
          >
          <span class="text-slate-300 text-xs">/100</span>
        </div>

        <div class="h-4 w-px bg-slate-200"></div>

        <!-- Gate -->
        <span class="badge {GATE_PILL[gColor]} gap-1">
          {GATE_LABEL[r.training_gate] ?? r.training_gate}
        </span>

        <div class="h-4 w-px bg-slate-200"></div>

        <!-- HRV -->
        {#if r.key_signals?.hrv?.deviation_pct != null}
          {@const hrv = r.key_signals.hrv.deviation_pct}
          <div class="flex items-center gap-1.5 text-xs">
            <span class="text-slate-400">HRV</span>
            <span class="font-semibold text-slate-200"
              >{r.key_signals?.hrv?.deviation_pct != null
                ? (r.key_signals.hrv.deviation_pct >= 0 ? "+" : "") +
                  r.key_signals.hrv.deviation_pct.toFixed(1) +
                  "%"
                : ""}</span
            >
          </div>
        {/if}

        <!-- Sleep -->
        {#if r.key_signals?.sleep?.score != null}
          <div class="flex items-center gap-1.5 text-xs">
            <span class="text-slate-400">Sleep</span>
            <span class="font-semibold text-slate-200"
              >{r.key_signals.sleep.score}/100</span
            >
          </div>
        {/if}

        <!-- Body battery -->
        {#if r.key_signals?.body_battery_morning != null}
          <div class="flex items-center gap-1.5 text-xs">
            <Zap size={12} class="text-yellow-500" />
            <span class="font-semibold text-slate-200"
              >{r.key_signals.body_battery_morning}</span
            >
          </div>
        {/if}
      </div>
    {:else}
      <div
        class="card px-5 py-3 text-sm text-slate-400 flex items-center gap-2"
      >
        <AlertTriangle size={14} class="text-amber-400" />
        No readiness data — run pipeline first.
      </div>
    {/if}

    <!-- ════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 3: Weekly Plan Grid                                      -->
    <!-- ════════════════════════════════════════════════════════════════ -->
    {#if $currentPlan}
      <div class="space-y-4">
        <!-- Header -->
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Calendar size={17} class="text-slate-400" />
            <h2 class="font-semibold text-slate-100">This Week's Plan</h2>
            <span class="text-xs text-slate-400">
              {$currentPlan.valid_from} → {$currentPlan.valid_to}
            </span>
          </div>
          <span class="text-xs text-slate-400"
            >{timeAgo($currentPlan.generated_at)}</span
          >
        </div>

        <!-- Week 1 -->
        {#if week1.length}
          <div>
            {#if w1Theme}
              <p
                class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2 pl-0.5"
              >
                Week 1 — {w1Theme}
              </p>
            {:else}
              <p
                class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2 pl-0.5"
              >
                Week 1
              </p>
            {/if}
            <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
              {#each week1 as session (session.date)}
                {@const isPast = session.date < today}
                {@const isToday = session.date === today}
                {@const isExpanded = expandedDates.has(session.date)}
                <div
                  role="button"
                  tabindex="0"
                  onclick={() => toggleSession(session.date)}
                  onkeydown={(e) =>
                    e.key === "Enter" && toggleSession(session.date)}
                  class="cursor-pointer rounded-xl border transition-all duration-150
                       {isToday
                    ? 'border-blue-500 bg-blue-900/30 shadow-sm shadow-blue-900/50'
                    : isPast
                      ? 'border-slate-700 bg-slate-800/50 opacity-60'
                      : 'border-slate-700 bg-slate-800 hover:border-slate-600 hover:shadow-sm'}
                       {isExpanded ? 'ring-2 ring-blue-300' : ''}"
                >
                  <!-- Day header -->
                  <div
                    class="px-2.5 pt-2.5 pb-1.5 border-b
                            {isToday
                      ? 'border-blue-700/50'
                      : 'border-slate-700'}"
                  >
                    <div class="flex items-center justify-between">
                      <span
                        class="text-xs font-semibold
                                 {isToday
                          ? 'text-blue-400'
                          : isPast
                            ? 'text-slate-500'
                            : 'text-slate-300'}"
                      >
                        {fmtHeader(session.date)}
                      </span>
                      {#if isPast && session.status === "completed"}
                        <CheckCircle
                          size={12}
                          class="text-green-500 shrink-0"
                        />
                      {:else if isToday}
                        <span class="w-1.5 h-1.5 rounded-full bg-blue-500"
                        ></span>
                      {/if}
                    </div>
                  </div>

                  <!-- Session summary -->
                  <div class="px-2.5 py-2">
                    {#if session.sport === "rest"}
                      <div class="text-center py-1">
                        <span class="text-xl">😴</span>
                        <p class="text-xs text-slate-400 mt-0.5">Rest</p>
                      </div>
                    {:else}
                      <div class="space-y-1">
                        <div class="flex items-center gap-1">
                          <span class="text-lg leading-none"
                            >{sportToEmoji(session.sport)}</span
                          >
                          <span class="text-xs text-slate-400 truncate"
                            >{session.sport}</span
                          >
                        </div>
                        <p
                          class="text-xs font-medium text-slate-200 truncate leading-snug"
                        >
                          {session.title}
                        </p>
                        <div class="flex items-center gap-1 flex-wrap">
                          {#if session.duration_min}
                            <span class="text-xs text-slate-400"
                              >{formatDuration(session.duration_min)}</span
                            >
                          {/if}
                          {#if session.intensity_zone}
                            <span
                              class="badge text-[10px] px-1.5 py-0 {ZONE_CLASS[
                                session.intensity_zone
                              ] ?? ''}"
                            >
                              {session.intensity_zone}
                            </span>
                          {/if}
                        </div>
                      </div>
                    {/if}
                    <!-- Expand indicator -->
                    {#if session.sport !== "rest"}
                      <ChevronRight
                        size={12}
                        class="text-slate-300 mt-1 transition-transform {isExpanded
                          ? 'rotate-90'
                          : ''}"
                      />
                    {/if}
                  </div>
                </div>

                <!-- Expanded accordion (spans full row via negative margin trick) -->
                {#if isExpanded}
                  <div
                    class="col-span-2 sm:col-span-4 lg:col-span-7 card p-4 -mt-1 space-y-3 text-sm"
                  >
                    <div class="flex items-start justify-between gap-4">
                      <div>
                        <h3 class="font-semibold text-slate-100">
                          {session.title}
                        </h3>
                        <p class="text-slate-400 italic text-xs mt-0.5">
                          {session.key_focus}
                        </p>
                      </div>
                      <div class="flex gap-1.5 shrink-0">
                        {#if session.intensity_zone}
                          <span
                            class="badge {ZONE_CLASS[session.intensity_zone] ??
                              ''}"
                          >
                            {session.intensity_zone}
                          </span>
                        {/if}
                        <span class="badge bg-slate-700 text-slate-300"
                          >{formatDuration(session.duration_min)}</span
                        >
                      </div>
                    </div>
                    <p class="text-slate-300 leading-relaxed">
                      {session.description}
                    </p>
                    {#if session.exercises && session.exercises.length > 0}
                      <div class="pt-2 border-t border-slate-700 space-y-1.5">
                        <p
                          class="text-xs font-semibold text-slate-400 uppercase tracking-wide"
                        >
                          Exercises
                        </p>
                        <div class="overflow-x-auto">
                          <table class="w-full text-xs">
                            <thead>
                              <tr class="text-left text-slate-500">
                                <th class="pb-1 pr-3 font-medium">Exercise</th>
                                <th class="pb-1 pr-3 font-medium w-10">Sets</th>
                                <th class="pb-1 pr-3 font-medium w-20"
                                  >Reps / Time</th
                                >
                                <th class="pb-1 font-medium">Notes</th>
                              </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-700/60">
                              {#each session.exercises as ex}
                                <tr class="align-top">
                                  <td
                                    class="py-1 pr-3 font-medium text-slate-200"
                                    >{ex.exercise}</td
                                  >
                                  <td class="py-1 pr-3 text-slate-400"
                                    >{ex.sets}</td
                                  >
                                  <td class="py-1 pr-3 text-slate-400"
                                    >{ex.reps_or_duration}</td
                                  >
                                  <td class="py-1 text-slate-500"
                                    >{ex.notes ?? "—"}</td
                                  >
                                </tr>
                              {/each}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    {/if}
                    {#if session.swim_sets && session.swim_sets.length > 0}
                      <div class="pt-2 border-t border-slate-700 space-y-1.5">
                        <p
                          class="text-xs font-semibold text-slate-400 uppercase tracking-wide"
                        >
                          Swim Sets
                        </p>
                        <div class="overflow-x-auto">
                          <table class="w-full text-xs">
                            <thead>
                              <tr class="text-left text-slate-500">
                                <th class="pb-1 pr-3 font-medium">Stroke</th>
                                <th class="pb-1 pr-3 font-medium">Volume</th>
                                <th class="pb-1 pr-3 font-medium w-14">Rest</th>
                                <th class="pb-1 pr-3 font-medium w-14">Zone</th>
                                <th class="pb-1 font-medium">Notes</th>
                              </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-700/60">
                              {#each session.swim_sets as set}
                                <tr class="align-top">
                                  <td
                                    class="py-1 pr-3 font-medium text-slate-200 capitalize"
                                    >{set.stroke}</td
                                  >
                                  <td class="py-1 pr-3 text-slate-400"
                                    >{set.reps} × {set.distance_m}m</td
                                  >
                                  <td class="py-1 pr-3 text-slate-400"
                                    >{set.rest_sec != null
                                      ? set.rest_sec + "s"
                                      : "—"}</td
                                  >
                                  <td class="py-1 pr-3 text-slate-400"
                                    >{set.intensity ?? "—"}</td
                                  >
                                  <td class="py-1 text-slate-500"
                                    >{set.notes ?? "—"}</td
                                  >
                                </tr>
                              {/each}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    {/if}
                    {#if session.nutrition}
                      <div
                        class="grid grid-cols-3 gap-3 pt-2 border-t border-slate-700"
                      >
                        {#each [["Pre", session.nutrition.pre_session], ["During", session.nutrition.during_session], ["Post", session.nutrition.post_session]] as [label, text]}
                          {#if text}
                            <div>
                              <p
                                class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-0.5"
                              >
                                {label}
                              </p>
                              <p class="text-xs text-slate-400">{text}</p>
                            </div>
                          {/if}
                        {/each}
                      </div>
                    {/if}
                  </div>
                {/if}
              {/each}
            </div>
          </div>
        {/if}

        <!-- Week 2 -->
        {#if week2.length}
          <div>
            {#if w2Theme}
              <p
                class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2 pl-0.5"
              >
                Week 2 — {w2Theme}
              </p>
            {:else}
              <p
                class="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2 pl-0.5"
              >
                Week 2
              </p>
            {/if}
            <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
              {#each week2 as session (session.date)}
                {@const isPast = session.date < today}
                {@const isExpanded = expandedDates.has(session.date)}
                <div
                  role="button"
                  tabindex="0"
                  onclick={() => toggleSession(session.date)}
                  onkeydown={(e) =>
                    e.key === "Enter" && toggleSession(session.date)}
                  class="cursor-pointer rounded-xl border transition-all duration-150
                       {isPast
                    ? 'border-slate-700 bg-slate-800/50 opacity-60'
                    : 'border-slate-700 bg-slate-800 hover:border-slate-600 hover:shadow-sm'}
                       {isExpanded ? 'ring-2 ring-blue-300' : ''}"
                >
                  <div class="px-2.5 pt-2.5 pb-1.5 border-b border-slate-700">
                    <span
                      class="text-xs font-semibold {isPast
                        ? 'text-slate-500'
                        : 'text-slate-300'}"
                    >
                      {fmtHeader(session.date)}
                    </span>
                  </div>
                  <div class="px-2.5 py-2">
                    {#if session.sport === "rest"}
                      <div class="text-center py-1">
                        <span class="text-xl">😴</span>
                        <p class="text-xs text-slate-400 mt-0.5">Rest</p>
                      </div>
                    {:else}
                      <div class="space-y-1">
                        <div class="flex items-center gap-1">
                          <span class="text-lg leading-none"
                            >{sportToEmoji(session.sport)}</span
                          >
                          <span class="text-xs text-slate-500 truncate"
                            >{session.sport}</span
                          >
                        </div>
                        <p class="text-xs font-medium text-slate-200 truncate">
                          {session.title}
                        </p>
                        <div class="flex items-center gap-1">
                          {#if session.duration_min}
                            <span class="text-xs text-slate-400"
                              >{formatDuration(session.duration_min)}</span
                            >
                          {/if}
                          {#if session.intensity_zone}
                            <span
                              class="badge text-[10px] px-1.5 py-0 {ZONE_CLASS[
                                session.intensity_zone
                              ] ?? ''}"
                            >
                              {session.intensity_zone}
                            </span>
                          {/if}
                        </div>
                      </div>
                    {/if}
                    {#if session.sport !== "rest"}
                      <ChevronRight
                        size={12}
                        class="text-slate-300 mt-1 transition-transform {isExpanded
                          ? 'rotate-90'
                          : ''}"
                      />
                    {/if}
                  </div>
                </div>

                {#if isExpanded}
                  <div
                    class="col-span-2 sm:col-span-4 lg:col-span-7 card p-4 -mt-1 space-y-3 text-sm"
                  >
                    <div class="flex items-start justify-between gap-4">
                      <div>
                        <h3 class="font-semibold text-slate-100">
                          {session.title}
                        </h3>
                        <p class="text-slate-400 italic text-xs mt-0.5">
                          {session.key_focus}
                        </p>
                      </div>
                      <div class="flex gap-1.5 shrink-0">
                        {#if session.intensity_zone}
                          <span
                            class="badge {ZONE_CLASS[session.intensity_zone] ??
                              ''}">{session.intensity_zone}</span
                          >
                        {/if}
                        <span class="badge bg-slate-700 text-slate-300"
                          >{formatDuration(session.duration_min)}</span
                        >
                      </div>
                    </div>
                    <p class="text-slate-300 leading-relaxed">
                      {session.description}
                    </p>
                    {#if session.exercises && session.exercises.length > 0}
                      <div class="pt-2 border-t border-slate-700 space-y-1.5">
                        <p
                          class="text-xs font-semibold text-slate-400 uppercase tracking-wide"
                        >
                          Exercises
                        </p>
                        <div class="overflow-x-auto">
                          <table class="w-full text-xs">
                            <thead>
                              <tr class="text-left text-slate-500">
                                <th class="pb-1 pr-3 font-medium">Exercise</th>
                                <th class="pb-1 pr-3 font-medium w-10">Sets</th>
                                <th class="pb-1 pr-3 font-medium w-20"
                                  >Reps / Time</th
                                >
                                <th class="pb-1 font-medium">Notes</th>
                              </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-700/60">
                              {#each session.exercises as ex}
                                <tr class="align-top">
                                  <td
                                    class="py-1 pr-3 font-medium text-slate-200"
                                    >{ex.exercise}</td
                                  >
                                  <td class="py-1 pr-3 text-slate-400"
                                    >{ex.sets}</td
                                  >
                                  <td class="py-1 pr-3 text-slate-400"
                                    >{ex.reps_or_duration}</td
                                  >
                                  <td class="py-1 text-slate-500"
                                    >{ex.notes ?? "—"}</td
                                  >
                                </tr>
                              {/each}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    {/if}
                    {#if session.swim_sets && session.swim_sets.length > 0}
                      <div class="pt-2 border-t border-slate-700 space-y-1.5">
                        <p
                          class="text-xs font-semibold text-slate-400 uppercase tracking-wide"
                        >
                          Swim Sets
                        </p>
                        <div class="overflow-x-auto">
                          <table class="w-full text-xs">
                            <thead>
                              <tr class="text-left text-slate-500">
                                <th class="pb-1 pr-3 font-medium">Stroke</th>
                                <th class="pb-1 pr-3 font-medium">Volume</th>
                                <th class="pb-1 pr-3 font-medium w-14">Rest</th>
                                <th class="pb-1 pr-3 font-medium w-14">Zone</th>
                                <th class="pb-1 font-medium">Notes</th>
                              </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-700/60">
                              {#each session.swim_sets as set}
                                <tr class="align-top">
                                  <td
                                    class="py-1 pr-3 font-medium text-slate-200 capitalize"
                                    >{set.stroke}</td
                                  >
                                  <td class="py-1 pr-3 text-slate-400"
                                    >{set.reps} × {set.distance_m}m</td
                                  >
                                  <td class="py-1 pr-3 text-slate-400"
                                    >{set.rest_sec != null
                                      ? set.rest_sec + "s"
                                      : "—"}</td
                                  >
                                  <td class="py-1 pr-3 text-slate-400"
                                    >{set.intensity ?? "—"}</td
                                  >
                                  <td class="py-1 text-slate-500"
                                    >{set.notes ?? "—"}</td
                                  >
                                </tr>
                              {/each}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    {/if}
                    {#if session.nutrition}
                      <div
                        class="grid grid-cols-3 gap-3 pt-2 border-t border-slate-700"
                      >
                        {#each [["Pre", session.nutrition.pre_session], ["During", session.nutrition.during_session], ["Post", session.nutrition.post_session]] as [label, text]}
                          {#if text}
                            <div>
                              <p
                                class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-0.5"
                              >
                                {label}
                              </p>
                              <p class="text-xs text-slate-400">{text}</p>
                            </div>
                          {/if}
                        {/each}
                      </div>
                    {/if}
                  </div>
                {/if}
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {/if}

    <!-- ════════════════════════════════════════════════════════════════ -->
    <!-- SECTION 4: Tomorrow Preview                                      -->
    <!-- ════════════════════════════════════════════════════════════════ -->
    {#if $tomorrowSession && $tomorrowSession.sport !== "rest"}
      {@const t = $tomorrowSession}
      <div class="card px-5 py-3.5 flex items-center gap-3">
        <span
          class="text-slate-400 text-xs font-semibold uppercase tracking-wide shrink-0"
          >Tomorrow</span
        >
        <span class="text-lg shrink-0">{sportToEmoji(t.sport)}</span>
        <span class="text-sm font-medium text-slate-200 truncate"
          >{t.title}</span
        >
        <div class="flex items-center gap-1.5 ml-auto shrink-0">
          {#if t.duration_min}
            <span class="badge bg-slate-700 text-slate-300 gap-1">
              <Clock size={11} />{formatDuration(t.duration_min)}
            </span>
          {/if}
          {#if t.intensity_zone}
            <span class="badge {ZONE_CLASS[t.intensity_zone] ?? ''}"
              >{t.intensity_zone}</span
            >
          {/if}
        </div>
      </div>
    {/if}
  {/if}
</div>

{#if $showOverrideModal && $todayReport}
  <OverrideModal
    report={$todayReport}
    open={$showOverrideModal}
    onrest={handleRest}
    onpush={handlePush}
    ondismiss={() => showOverrideModal.set(false)}
  />
{/if}

<style>
  @keyframes fade-in {
    from {
      opacity: 0;
      transform: translateY(6px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  .animate-fade-in {
    animation: fade-in 0.3s ease-out both;
  }
  @keyframes pulse-border {
    0%,
    100% {
      border-color: #fbbf24;
    }
    50% {
      border-color: #f97316;
    }
  }
  .animate-pulse-border {
    animation: pulse-border 2s ease-in-out infinite;
  }
</style>
