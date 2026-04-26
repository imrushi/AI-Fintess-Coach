<script lang="ts">
  import { onMount } from "svelte";
  import {
    userId,
    todayReport,
    currentPlan,
    todaySession,
    addToast,
  } from "$lib/stores";
  import { submitCheckIn, getTodayCheckIn, getCurrentPlan } from "$lib/api";
  import type { CheckInRequest } from "$lib/types";
  import { todayStr, sportToEmoji } from "$lib/types";
  import {
    MessageSquare,
    Gauge,
    Heart,
    Send,
    CheckCircle,
  } from "lucide-svelte";

  // ── State ─────────────────────────────────────────────────────────────
  let loading = $state(false);
  let submitted = $state(false);
  let existingCheckIn = $state<any>(null);
  let planUpdated = $state(false);

  let form = $state({
    perceived_effort: null as number | null,
    mood: null as number | null,
    free_text: "",
    override_choice: null as string | null,
    override_reason: "",
  });

  // ── Yesterday's session ───────────────────────────────────────────────
  const yesterdayStr = $derived(() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return d.toISOString().split("T")[0];
  });

  const yesterdaySession = $derived(
    $currentPlan?.sessions.find((s) => s.date === yesterdayStr()) ?? null,
  );

  // ── RPE helpers ───────────────────────────────────────────────────────
  const RPE_LABELS: Record<number, string> = {
    1: "Very easy",
    2: "Easy",
    3: "Light",
    4: "Comfortable",
    5: "Moderate",
    6: "Somewhat hard",
    7: "Hard",
    8: "Very hard",
    9: "Very very hard",
    10: "Maximum effort",
  };

  function rpeLabel(v: number | null): string {
    return v != null ? (RPE_LABELS[v] ?? "") : "";
  }

  function rpeThumbColor(v: number | null): string {
    if (v == null) return "accent-slate-400";
    if (v <= 4) return "accent-green-500";
    if (v <= 6) return "accent-yellow-500";
    if (v <= 8) return "accent-orange-500";
    return "accent-red-500";
  }

  function rpeTextColor(v: number | null): string {
    if (v == null) return "text-slate-400";
    if (v <= 4) return "text-green-600";
    if (v <= 6) return "text-yellow-600";
    if (v <= 8) return "text-orange-600";
    return "text-red-600";
  }

  // ── Mood selector ─────────────────────────────────────────────────────
  const MOODS = [
    { value: 1, emoji: "😞", label: "Rough" },
    { value: 2, emoji: "😕", label: "Low" },
    { value: 3, emoji: "😐", label: "Okay" },
    { value: 4, emoji: "🙂", label: "Good" },
    { value: 5, emoji: "😄", label: "Great" },
  ];

  // ── Disabled check ────────────────────────────────────────────────────
  const canSubmit = $derived(
    !loading &&
      (form.perceived_effort != null ||
        form.mood != null ||
        form.free_text.trim().length > 0),
  );

  // ── Load existing check-in on mount ───────────────────────────────────
  onMount(async () => {
    const uid = $userId;
    if (!uid) return;
    try {
      const existing = await getTodayCheckIn(uid);
      if (existing) {
        existingCheckIn = existing;
        submitted = true;
      }
    } catch (e: unknown) {
      // no check-in yet — silent
    }
  });

  // ── Submit handler ────────────────────────────────────────────────────
  async function handleSubmit() {
    const uid = $userId;
    if (!uid || !canSubmit) return;
    loading = true;
    planUpdated = false;
    try {
      const req: CheckInRequest = {
        user_id: uid,
        check_in_date: todayStr(),
        perceived_effort: form.perceived_effort,
        mood: form.mood,
        free_text: form.free_text.trim() || null,
        override_choice: form.override_choice as
          | "rest_as_recommended"
          | "push_through"
          | null,
        override_reason: form.override_reason.trim() || null,
      };
      const res = await submitCheckIn(req);
      existingCheckIn = res;
      submitted = true;
      if (res.plan_updated) {
        planUpdated = true;
        const uid2 = $userId;
        if (uid2) {
          const plan = await getCurrentPlan(uid2);
          currentPlan.set(plan);
        }
      }
    } catch (e: unknown) {
      addToast(
        e instanceof Error ? e.message : "Failed to save check-in",
        "error",
      );
    } finally {
      loading = false;
    }
  }

  // ── Today's date display ──────────────────────────────────────────────
  const todayDisplay = new Date().toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
</script>

<div class="max-w-2xl mx-auto py-8 px-4 space-y-6 animate-fade-in">
  <!-- ══ HEADER ══════════════════════════════════════════════════════════ -->
  <div>
    <h1 class="text-2xl font-bold text-slate-100 flex items-center gap-2">
      <MessageSquare size={22} class="text-blue-500" />
      Daily Check-in
    </h1>
    <p class="text-slate-400 text-sm mt-1">
      {todayDisplay} — How are you feeling?
    </p>
  </div>

  <!-- ══ PLAN UPDATED TOAST ═══════════════════════════════════════════════ -->
  {#if planUpdated}
    <div
      class="flex items-center gap-3 bg-green-900/30 border border-green-700/50 rounded-xl px-4 py-3 text-sm text-green-400"
    >
      <CheckCircle size={16} class="shrink-0" />
      Plan updated based on your check-in
    </div>
  {/if}

  <!-- ══ SUCCESS BANNER ═══════════════════════════════════════════════════ -->
  {#if submitted && existingCheckIn}
    <div class="card border-green-700/50 border bg-green-900/20 p-4 space-y-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2 text-green-400 font-medium text-sm">
          <CheckCircle size={16} />
          Check-in recorded for today
        </div>
        <button
          onclick={() => {
            submitted = false;
          }}
          class="text-xs text-slate-400 hover:text-slate-200 underline transition"
        >
          Edit
        </button>
      </div>
      <!-- Summary -->
      <div class="flex flex-wrap gap-3 text-sm">
        {#if existingCheckIn.perceived_effort != null}
          <div
            class="flex items-center gap-1.5 bg-slate-700 rounded-lg border border-slate-600 px-3 py-1.5"
          >
            <Gauge size={13} class="text-slate-400" />
            <span class="text-slate-400">RPE</span>
            <span class="font-semibold text-slate-200"
              >{existingCheckIn.perceived_effort}/10</span
            >
          </div>
        {/if}
        {#if existingCheckIn.mood != null}
          {@const m = MOODS.find((m) => m.value === existingCheckIn.mood)}
          <div
            class="flex items-center gap-1.5 bg-slate-700 rounded-lg border border-slate-600 px-3 py-1.5"
          >
            <span>{m?.emoji}</span>
            <span class="text-slate-300">{m?.label}</span>
          </div>
        {/if}
        {#if existingCheckIn.override_applied}
          <div
            class="flex items-center gap-1.5 bg-slate-700 rounded-lg border border-amber-700/50 px-3 py-1.5 text-amber-400"
          >
            Override: {existingCheckIn.override_applied.replace(/_/g, " ")}
          </div>
        {/if}
      </div>
    </div>
  {/if}

  {#if !submitted}
    <!-- ══ YESTERDAY REFERENCE ════════════════════════════════════════════ -->
    {#if yesterdaySession}
      {@const ys = yesterdaySession}
      <div class="card px-4 py-3 flex items-center gap-3">
        <span class="text-2xl leading-none" role="img" aria-label={ys.sport}
          >{sportToEmoji(ys.sport)}</span
        >
        <div class="min-w-0">
          <p class="text-xs text-slate-400 font-medium uppercase tracking-wide">
            Yesterday's session
          </p>
          <p class="text-sm font-medium text-slate-200 truncate">
            {ys.title}
            {#if ys.duration_min}
              <span class="text-slate-400 font-normal">
                · {ys.duration_min}min</span
              >
            {/if}
            {#if ys.intensity_zone}
              <span class="text-slate-400 font-normal">
                · {ys.intensity_zone}</span
              >
            {/if}
          </p>
        </div>
      </div>
    {/if}

    <!-- ══ RPE SLIDER ═════════════════════════════════════════════════════ -->
    <div class="card p-6 space-y-4">
      <div class="flex items-center gap-2">
        <Gauge size={18} class="text-slate-400 shrink-0" />
        <div>
          <p class="font-semibold text-slate-100 text-sm">
            Rate yesterday's effort
          </p>
          <p class="text-xs text-slate-400">
            RPE 1–10 (Rating of Perceived Exertion)
          </p>
        </div>
      </div>

      <!-- Slider -->
      <div class="space-y-2">
        <input
          type="range"
          min="1"
          max="10"
          step="1"
          bind:value={form.perceived_effort}
          class="w-full h-2 rounded-full appearance-none bg-gradient-to-r cursor-pointer
                 {form.perceived_effort == null
            ? 'from-slate-200 to-slate-200'
            : form.perceived_effort <= 4
              ? 'from-green-200 to-green-400'
              : form.perceived_effort <= 6
                ? 'from-yellow-200 to-yellow-400'
                : form.perceived_effort <= 8
                  ? 'from-orange-200 to-orange-400'
                  : 'from-red-200 to-red-500'}
                 {rpeThumbColor(form.perceived_effort)}"
        />

        <!-- Value + label -->
        <div class="flex items-baseline gap-2">
          {#if form.perceived_effort != null}
            <span
              class="text-4xl font-bold tabular-nums leading-none {rpeTextColor(
                form.perceived_effort,
              )}"
            >
              {form.perceived_effort}
            </span>
            <span class="text-sm text-slate-400"
              >— {rpeLabel(form.perceived_effort)}</span
            >
          {:else}
            <span class="text-sm text-slate-300 italic"
              >Drag the slider to rate your effort</span
            >
          {/if}
        </div>
      </div>

      <!-- RPE zone hints -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
        {#each [{ range: "1–3", label: "Recovery", color: "text-green-400 bg-green-900/40 border-green-700/50" }, { range: "4–5", label: "Aerobic", color: "text-yellow-400 bg-yellow-900/40 border-yellow-700/50" }, { range: "6–7", label: "Moderate", color: "text-orange-400 bg-orange-900/40 border-orange-700/50" }, { range: "8–10", label: "Hard / Max", color: "text-red-400 bg-red-900/40 border-red-700/50" }] as hint}
          <div class="rounded-lg border px-2.5 py-1.5 text-center {hint.color}">
            <p class="text-xs font-bold">{hint.range}</p>
            <p class="text-xs">{hint.label}</p>
          </div>
        {/each}
      </div>
    </div>

    <!-- ══ MOOD SELECTOR ═════════════════════════════════════════════════ -->
    <div class="card p-6 space-y-4">
      <div class="flex items-center gap-2">
        <Heart size={18} class="text-slate-400 shrink-0" />
        <p class="font-semibold text-slate-100 text-sm">Overall mood today</p>
      </div>

      <div class="flex justify-between gap-2">
        {#each MOODS as m}
          <button
            onclick={() => (form.mood = form.mood === m.value ? null : m.value)}
            class="flex-1 flex flex-col items-center gap-1 py-3 rounded-xl border transition-all duration-150 select-none
                   {form.mood === m.value
              ? 'ring-2 ring-blue-500 border-blue-500 bg-blue-900/30 scale-110 shadow-sm'
              : 'border-slate-600 bg-slate-700 hover:scale-105 hover:border-slate-500 hover:shadow-sm'}"
          >
            <span class="text-2xl leading-none">{m.emoji}</span>
            <span class="text-xs text-slate-400 font-medium">{m.label}</span>
          </button>
        {/each}
      </div>
    </div>

    <!-- ══ FREE TEXT ══════════════════════════════════════════════════════ -->
    <div class="card p-6 space-y-3">
      <div class="flex items-center gap-2">
        <MessageSquare size={18} class="text-slate-400 shrink-0" />
        <div>
          <p class="font-semibold text-slate-100 text-sm">
            How did it feel? <span class="text-slate-400 font-normal"
              >(optional)</span
            >
          </p>
        </div>
      </div>

      <div class="relative">
        <textarea
          bind:value={form.free_text}
          maxlength={500}
          rows={4}
          placeholder="Any notes on the session — what felt good, what was hard, how your body felt, anything unusual..."
          class="w-full rounded-lg border border-slate-600 px-3.5 py-3 text-sm text-slate-200
                 bg-slate-700 placeholder:text-slate-500 resize-none focus:outline-none focus:ring-2
                 focus:ring-blue-400 focus:border-transparent transition leading-relaxed"
        ></textarea>
        <p class="text-right text-xs text-slate-300 mt-1">
          {form.free_text.length} / 500
        </p>
      </div>
    </div>

    <!-- ══ SUBMIT ═════════════════════════════════════════════════════════ -->
    <button
      onclick={handleSubmit}
      disabled={!canSubmit}
      class="w-full btn-primary flex items-center justify-center gap-2 py-3.5 text-base
             disabled:opacity-50 disabled:cursor-not-allowed transition"
    >
      {#if loading}
        <span
          class="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin"
        ></span>
        Saving…
      {:else}
        <Send size={16} />
        Save Check-in
      {/if}
    </button>
  {/if}<!-- end !submitted -->

  <!-- ══ WHAT HAPPENS NEXT ══════════════════════════════════════════════ -->
  <div class="pt-2 space-y-3">
    <p class="text-xs text-slate-400 leading-relaxed text-center">
      Your check-in feeds into tomorrow's readiness analysis and automatically
      adjusts your training plan if needed.
    </p>
    <div class="grid grid-cols-3 gap-3">
      {#each [{ icon: "📊", title: "RPE tracked", desc: "Effort logged for load analysis" }, { icon: "😴", title: "Recovery monitored", desc: "Fatigue trends updated" }, { icon: "🔄", title: "Plan adapts daily", desc: "Tomorrow adjusts automatically" }] as card}
        <div class="card p-3 text-center space-y-1">
          <span class="text-xl">{card.icon}</span>
          <p class="text-xs font-semibold text-slate-300">{card.title}</p>
          <p class="text-xs text-slate-400 leading-snug">{card.desc}</p>
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  @keyframes fade-in {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  .animate-fade-in {
    animation: fade-in 0.3s ease-out both;
  }

  /* Range input cross-browser thumb styling */
  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: white;
    border: 2px solid #94a3b8;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
    cursor: pointer;
    transition:
      border-color 0.15s,
      transform 0.15s;
  }
  input[type="range"]::-webkit-slider-thumb:hover {
    transform: scale(1.15);
    border-color: #3b82f6;
  }
  input[type="range"]::-moz-range-thumb {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: white;
    border: 2px solid #94a3b8;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
    cursor: pointer;
    transition:
      border-color 0.15s,
      transform 0.15s;
  }
</style>
