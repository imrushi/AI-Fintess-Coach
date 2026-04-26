<script lang="ts">
  import "../app.css";
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import {
    userId,
    todayReport,
    currentPlan,
    globalError,
    isLoading,
    pipelineRunning,
    overridePrompt,
    toasts,
    addToast,
    dismissToast,
  } from "$lib/stores";
  import {
    getCurrentPlan,
    getReadinessReport,
    getOverridePrompt,
    getStoredUserId,
    storeUserId,
    runFullPipeline,
  } from "$lib/api";
  import { gateToColor, todayStr } from "$lib/types";

  let { children } = $props();
  const devId = import.meta.env.VITE_DEV_USER_ID;
  if (devId) storeUserId(devId);

  // ── Route → page title map ──────────────────────────────────────────
  const ROUTE_TITLES: Record<string, string> = {
    "/": "Dashboard",
    "/checkin": "Daily Check-in",
    "/stats": "Performance",
    "/settings": "Settings",
  };
  let pageTitle = $derived(ROUTE_TITLES[$page.url.pathname] ?? "FitCoach AI");

  // ── Active route detection ──────────────────────────────────────────
  function isActive(path: string): boolean {
    if (path === "/") return $page.url.pathname === "/";
    return (
      $page.url.pathname === path || $page.url.pathname.startsWith(path + "/")
    );
  }

  // ── Error auto-dismiss (keep for backward compat) ───────────────────
  let errorTimer: ReturnType<typeof setTimeout>;
  $effect(() => {
    if ($globalError) {
      addToast($globalError, "error");
      clearTimeout(errorTimer);
      errorTimer = setTimeout(() => globalError.set(null), 100);
    }
  });

  // ── Gate color → Tailwind class ─────────────────────────────────────
  const gateClasses: Record<string, string> = {
    green: "bg-green-500",
    yellow: "bg-yellow-400",
    orange: "bg-orange-500",
    red: "bg-red-500",
  };
  let gateBg = $derived(
    $todayReport
      ? (gateClasses[gateToColor($todayReport.training_gate)] ?? "bg-slate-400")
      : "bg-slate-400",
  );

  // ── Data freshness ──────────────────────────────────────────────────
  function timeAgo(dateStr: string | undefined): {
    label: string;
    cls: string;
  } {
    if (!dateStr) return { label: "Never", cls: "text-slate-500" };
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const d = new Date(dateStr + "T00:00:00");
    const days = Math.round((today.getTime() - d.getTime()) / 86400000);
    if (days === 0) return { label: "Today", cls: "text-green-400" };
    if (days === 1) return { label: "Yesterday", cls: "text-amber-400" };
    return {
      label: `${days} days ago`,
      cls: days > 2 ? "text-red-400" : "text-amber-400",
    };
  }
  let freshness = $derived(timeAgo($todayReport?.report_date));

  // ── Nav links ───────────────────────────────────────────────────────
  const NAV_DESKTOP = [
    { href: "/", label: "Dashboard", icon: "🏠" },
    { href: "/checkin", label: "Check-in", icon: "✅" },
    { href: "/stats", label: "Performance", icon: "📊" },
    { href: "/settings", label: "Settings", icon: "⚙️" },
  ];
  const NAV_MOBILE = [
    { href: "/", label: "Dashboard", icon: "🏠" },
    { href: "/checkin", label: "Check-in", icon: "✅" },
    { href: "/stats", label: "Stats", icon: "📊" },
    { href: "/settings", label: "Settings", icon: "⚙️" },
  ];

  // ── Pipeline run ────────────────────────────────────────────────────
  async function handleRunPipeline() {
    if (!$userId || $pipelineRunning) return;
    pipelineRunning.set(true);
    try {
      const result = await runFullPipeline($userId);
      if (!result.success) {
        addToast(result.error ?? "Pipeline failed", "error");
        return;
      }
      const [planRes, reportRes] = await Promise.allSettled([
        getCurrentPlan($userId),
        getReadinessReport($userId),
      ]);
      if (planRes.status === "fulfilled") currentPlan.set(planRes.value);
      if (reportRes.status === "fulfilled") todayReport.set(reportRes.value);
      addToast("Pipeline complete — plan updated", "success");
    } catch (e: unknown) {
      addToast(e instanceof Error ? e.message : "Pipeline failed", "error");
    } finally {
      pipelineRunning.set(false);
    }
  }

  // ── Keyboard shortcut ───────────────────────────────────────────────
  function handleKeydown(e: KeyboardEvent) {
    const target = e.target as HTMLElement;
    const inInput = ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
    if (!inInput && e.key === "r" && !e.metaKey && !e.ctrlKey) {
      handleRunPipeline();
    }
  }

  // ── Bootstrap on mount ──────────────────────────────────────────────
  onMount(async () => {
    let uid = getStoredUserId();
    if (!uid) {
      uid = import.meta.env.VITE_DEV_USER_ID ?? null;
      if (uid) storeUserId(uid);
    }
    if (!uid) return;
    userId.set(uid);

    isLoading.set(true);
    try {
      const [planRes, reportRes, overrideRes] = await Promise.allSettled([
        getCurrentPlan(uid),
        getReadinessReport(uid),
        getOverridePrompt(uid),
      ]);
      if (planRes.status === "fulfilled") currentPlan.set(planRes.value);
      if (reportRes.status === "fulfilled") todayReport.set(reportRes.value);
      if (overrideRes.status === "fulfilled")
        overridePrompt.set(overrideRes.value);
    } finally {
      isLoading.set(false);
    }
  });

  // ── Toast icon helper ───────────────────────────────────────────────
  function toastIcon(type: string): string {
    if (type === "success") return "✓";
    if (type === "error") return "✕";
    return "ℹ";
  }
  function toastBg(type: string): string {
    if (type === "success") return "bg-green-600";
    if (type === "error") return "bg-red-600";
    return "bg-slate-700";
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<svelte:head>
  <title>{pageTitle} — FitCoach AI</title>
</svelte:head>

<!-- ── Loading progress bar ───────────────────────────────────────────── -->
{#if $isLoading || $pipelineRunning}
  <div
    class="fixed top-0 left-0 right-0 z-50 h-0.5 bg-blue-100 overflow-hidden"
  >
    <div class="h-full bg-blue-500 animate-pulse w-2/3"></div>
  </div>
{/if}

<!-- ── Toast stack ────────────────────────────────────────────────────── -->
{#if $toasts.length > 0}
  <div
    class="fixed z-50 flex flex-col gap-2
              top-4 left-1/2 -translate-x-1/2 w-[calc(100vw-2rem)] max-w-sm
              md:left-auto md:translate-x-0 md:right-6 md:top-auto md:bottom-6"
  >
    {#each $toasts as toast (toast.id)}
      <div
        class="flex items-start gap-2.5 px-4 py-3 rounded-xl shadow-lg text-sm font-medium text-white
                  {toastBg(toast.type)} animate-slide-up"
      >
        <span
          class="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center text-xs shrink-0 mt-0.5"
        >
          {toastIcon(toast.type)}
        </span>
        <span class="flex-1 leading-snug">{toast.message}</span>
        <button
          onclick={() => dismissToast(toast.id)}
          class="text-white/60 hover:text-white text-base leading-none shrink-0"
          aria-label="Dismiss">✕</button
        >
      </div>
    {/each}
  </div>
{/if}

<!-- ── Root layout ────────────────────────────────────────────────────── -->
<div class="min-h-screen flex">
  <!-- ── Desktop sidebar (lg+) ──────────────────────────────────────── -->
  <aside
    class="hidden lg:flex flex-col fixed left-0 top-0 bottom-0 w-64
                bg-slate-900 border-r border-slate-700/60 text-white z-40"
  >
    <!-- Logo -->
    <div class="px-6 py-5 border-b border-white/10 flex items-center gap-2">
      <span class="text-yellow-400 text-xl">⚡</span>
      <span class="font-display font-bold text-lg tracking-tight"
        >FitCoach AI</span
      >
    </div>

    <!-- Nav links -->
    <nav class="flex-1 px-3 py-4 space-y-1">
      {#each NAV_DESKTOP as link}
        {@const active = isActive(link.href)}
        <a
          href={link.href}
          class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium
                 transition-all duration-150
                 {active
            ? 'bg-blue-600/10 text-blue-400 border-l-4 border-blue-500 pl-[8px]'
            : 'text-slate-400 hover:text-white hover:bg-white/5 border-l-4 border-transparent pl-[8px]'}"
        >
          <span class="text-base w-5 text-center">{link.icon}</span>
          {link.label}
        </a>
      {/each}
    </nav>

    <!-- Readiness pill + data freshness -->
    <div class="px-5 py-4 border-t border-white/10 space-y-2">
      {#if $todayReport}
        <div class="flex items-center gap-3">
          <div class="w-2.5 h-2.5 rounded-full flex-shrink-0 {gateBg}"></div>
          <div class="min-w-0">
            <p class="text-xs text-slate-400 leading-tight">
              Today's Readiness
            </p>
            <p class="text-white font-semibold text-sm leading-tight truncate">
              {$todayReport.readiness_score}/100
              <span class="font-normal text-slate-400"
                >· {$todayReport.training_gate.replace(/_/g, " ")}</span
              >
            </p>
          </div>
        </div>
        <p class="text-xs {freshness.cls}">Last updated: {freshness.label}</p>
      {:else}
        <p class="text-xs text-slate-500">No readiness data yet</p>
      {/if}
    </div>

    <!-- Keyboard shortcut hint -->
    <div class="px-5 pb-4">
      <p class="text-xs text-slate-600 font-mono">R — Run Pipeline</p>
    </div>
  </aside>

  <!-- ── Main content area ──────────────────────────────────────────── -->
  <div class="flex-1 flex flex-col lg:ml-64 min-h-screen">
    <!-- Top bar -->
    <header
      class="hidden lg:flex items-center justify-between
                   px-6 py-4 bg-slate-900 border-b border-slate-700/60 sticky top-0 z-30"
    >
      <h1 class="text-lg font-semibold text-slate-100">{pageTitle}</h1>
      <button
        onclick={handleRunPipeline}
        disabled={$pipelineRunning}
        class="btn-primary flex items-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {#if $pipelineRunning}
          <span
            class="inline-block w-3.5 h-3.5 border-2 border-white/40 border-t-white
                       rounded-full animate-spin"
          ></span>
          Running…
        {:else}
          <span>⚡</span> Run Pipeline
        {/if}
      </button>
    </header>

    <!-- Page content -->
    <main class="flex-1 overflow-y-auto pb-20 lg:pb-0">
      {@render children()}
    </main>
  </div>

  <!-- ── Mobile bottom tab bar ──────────────────────────────────────── -->
  <nav
    class="lg:hidden fixed bottom-0 left-0 right-0 z-40
              bg-slate-900 border-t border-slate-700/60 shadow-lg
              flex items-stretch"
  >
    {#each NAV_MOBILE as tab}
      {@const active = isActive(tab.href)}
      <a
        href={tab.href}
        class="flex-1 flex flex-col items-center justify-center py-2 gap-0.5 text-xs font-medium
               transition-colors
               {active
          ? 'text-blue-500'
          : 'text-slate-400 hover:text-slate-200'}"
      >
        <span class="text-lg leading-tight">{tab.icon}</span>
        <span class="leading-tight">{tab.label}</span>
      </a>
    {/each}
  </nav>
</div>

<style>
  @keyframes slide-up {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  .animate-slide-up {
    animation: slide-up 0.2s ease-out both;
  }
</style>
