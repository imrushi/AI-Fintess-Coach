<script lang="ts">
  import { X, Zap, Moon, Minus, Activity } from "lucide-svelte";
  import type { ReadinessReport } from "$lib/types";
  import { gateToColor, readinessToColor } from "$lib/types";

  interface Props {
    report: ReadinessReport | null;
    open?: boolean;
    loading?: boolean;
    onsubmit?: (intensity: string) => void;
    ondismiss?: () => void;
  }

  let {
    report,
    open = false,
    loading = false,
    onsubmit,
    ondismiss,
  }: Props = $props();

  const INTENSITY_OPTIONS = [
    {
      value: "easy",
      label: "Easy",
      description: "Zone 1–2, shorter duration. Good if feeling off.",
      icon: Moon,
      color: "border-blue-400 text-blue-300",
      bg: "bg-blue-900/30",
    },
    {
      value: "moderate",
      label: "Moderate",
      description: "Balanced effort adjusted to today's readiness.",
      icon: Activity,
      color: "border-slate-400 text-slate-300",
      bg: "bg-slate-700/30",
    },
    {
      value: "hard",
      label: "Hard",
      description: "Push Zone 3–4. Only if you feel strong.",
      icon: Zap,
      color: "border-orange-400 text-orange-300",
      bg: "bg-orange-900/30",
    },
    {
      value: "as_planned",
      label: "As Planned",
      description: "Keep the original session unchanged.",
      icon: Minus,
      color: "border-green-400 text-green-300",
      bg: "bg-green-900/30",
    },
    {
      value: "rest",
      label: "Rest",
      description: "Replace with active recovery or full rest.",
      icon: Moon,
      color: "border-red-400 text-red-300",
      bg: "bg-red-900/30",
    },
  ] as const;

  let selected = $state<string>("moderate");

  const GATE_PILL: Record<string, string> = {
    green: "bg-green-900/40 text-green-300 border border-green-500/40",
    yellow: "bg-yellow-900/40 text-yellow-300 border border-yellow-500/40",
    orange: "bg-orange-900/40 text-orange-300 border border-orange-500/40",
    red: "bg-red-900/40 text-red-300 border border-red-500/40",
  };

  function handleSubmit() {
    onsubmit?.(selected);
  }
</script>

{#if open}
  <!-- Backdrop -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
  >
    <div
      class="relative w-full max-w-md mx-4 card p-6 space-y-5 animate-fade-in"
    >
      <!-- Close -->
      <button
        onclick={ondismiss}
        class="absolute top-4 right-4 text-slate-400 hover:text-slate-200 transition-colors"
        aria-label="Close"
      >
        <X class="w-5 h-5" />
      </button>

      <!-- Header -->
      <div>
        <h2 class="text-lg font-bold text-slate-100">Update Today's Session</h2>
        <p class="text-sm text-slate-400 mt-1">
          Regenerate today's workout with your preferred intensity.
        </p>
      </div>

      <!-- Readiness summary -->
      {#if report}
        <div
          class="rounded-lg bg-slate-800/60 border border-slate-700/50 p-4 space-y-2"
        >
          <div class="flex items-center justify-between">
            <span class="text-sm text-slate-400">Today's Readiness</span>
            <span
              class="text-xl font-bold {readinessToColor(
                report.readiness_score,
              )}"
            >
              {report.readiness_score}/100
            </span>
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <span
              class="text-xs px-2 py-0.5 rounded-full {GATE_PILL[
                gateToColor(report.training_gate)
              ]}"
            >
              {report.training_gate.replace(/_/g, " ")}
            </span>
            {#each (report.flags ?? []).slice(0, 3) as flag}
              <span
                class="text-xs px-2 py-0.5 rounded-full bg-slate-700/50 text-slate-400 border border-slate-600/40"
              >
                {flag.replace(/_/g, " ")}
              </span>
            {/each}
          </div>
          {#if report.narrative}
            <p class="text-xs text-slate-400 leading-relaxed line-clamp-2">
              {report.narrative}
            </p>
          {/if}
        </div>
      {:else}
        <div class="rounded-lg bg-slate-800/60 border border-slate-700/50 p-4">
          <p class="text-sm text-slate-400">
            No readiness report for today. Using most recent available.
          </p>
        </div>
      {/if}

      <!-- Intensity selector -->
      <div class="space-y-2">
        <p class="text-sm font-medium text-slate-300">Choose intensity</p>
        <div class="space-y-2">
          {#each INTENSITY_OPTIONS as opt}
            <button
              onclick={() => (selected = opt.value)}
              class="w-full text-left rounded-lg border px-4 py-3 transition-all
                {selected === opt.value
                ? `${opt.bg} ${opt.color} ring-1 ring-current`
                : 'border-slate-700/50 bg-slate-800/40 text-slate-400 hover:border-slate-600'}"
            >
              <div class="flex items-center gap-3">
                <opt.icon class="w-4 h-4 shrink-0" />
                <div>
                  <span class="text-sm font-medium">{opt.label}</span>
                  <p class="text-xs opacity-75 mt-0.5">{opt.description}</p>
                </div>
                {#if selected === opt.value}
                  <span class="ml-auto text-xs font-medium">✓</span>
                {/if}
              </div>
            </button>
          {/each}
        </div>
      </div>

      <!-- Actions -->
      <div class="flex gap-3 pt-1">
        <button
          onclick={ondismiss}
          class="flex-1 btn-secondary py-2 text-sm"
          disabled={loading}
        >
          Cancel
        </button>
        <button
          onclick={handleSubmit}
          class="flex-1 btn-primary py-2 text-sm"
          disabled={loading}
        >
          {#if loading}
            <span
              class="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2"
            ></span>
            Updating…
          {:else}
            Update Today
          {/if}
        </button>
      </div>
    </div>
  </div>
{/if}
