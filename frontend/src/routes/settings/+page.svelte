<script lang="ts">
  import { onMount } from "svelte";
  import {
    userId,
    userProfile,
    currentPlan,
    todayReport,
    addToast,
  } from "$lib/stores";
  import {
    getProfile,
    updateProfile,
    getSchedulerStatus,
    triggerSync,
    triggerPipeline,
    clearCurrentPlan,
    resetAllData,
  } from "$lib/api";
  import type { SchedulerStatus, UserProfile } from "$lib/types";
  import {
    User,
    Target,
    Brain,
    Calendar,
    Clock,
    Save,
    RefreshCw,
    CheckCircle,
    AlertCircle,
    AlertTriangle,
    ChevronDown,
    ChevronUp,
    Zap,
    Info,
  } from "lucide-svelte";

  // ── State ─────────────────────────────────────────────────────────────
  let profile = $state<UserProfile | null>(null);
  let schedulerStatus = $state<SchedulerStatus | null>(null);
  let loading = $state(true);
  let saving = $state(false);
  let saveSuccess = $state(false);
  let syncTriggering = $state(false);
  let pipelineTriggering = $state(false);
  let activeSection = $state<string>("profile");

  // ── Toast ─────────────────────────────────────────────────────────────
  let toast = $state<{ message: string; kind: "success" | "error" } | null>(
    null,
  );
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  function showToast(message: string, kind: "success" | "error" = "success") {
    toast = { message, kind };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast = null;
    }, 3500);
  }

  // ── Form ──────────────────────────────────────────────────────────────
  let form = $state({
    display_name: "",
    goal_event: "",
    goal_date: "",
    fitness_level: "",
    medical_conditions: "",
    dietary_preference: "",
    dietary_allergies: "",
    max_weekly_hours: "",
    date_of_birth: "",
    lthr: "",
    garmin_email: "",
    garmin_password: "",
    swim_equipment: "",
    swim_strokes: "",
    model_analysis: "",
    model_planning: "",
  });

  // snapshot of saved values for dirty tracking — use separate state vars to avoid spread warning
  let savedFormJson = $state("");

  const isDirty = $derived(JSON.stringify(form) !== savedFormJson);

  const modelChanged = $derived.by(() => {
    if (!profile) return false;
    return (
      form.model_analysis !== (profile.model_analysis ?? "") ||
      form.model_planning !== (profile.model_planning ?? "")
    );
  });

  // ── Danger zone confirm state ─────────────────────────────────────────
  let clearPlanConfirming = $state(false);
  let resetConfirming = $state(false);
  let resetTypedWord = $state("");
  let clearPlanLoading = $state(false);
  let resetLoading = $state(false);

  // ── Model cost table ──────────────────────────────────────────────────
  const MODEL_COST: Record<string, string> = {
    "openrouter/anthropic/claude-3-5-sonnet-20241022": "~$0.004/day",
    "openrouter/anthropic/claude-3-haiku-20240307": "~$0.0005/day",
    "openrouter/google/gemini-flash-1.5": "~$0.0002/day",
    "openrouter/meta-llama/llama-3.1-70b-instruct": "~$0.001/day",
  };

  function modelCostLabel(model: string): string {
    if (model.startsWith("ollama/")) return "$0.00/day (local)";
    return MODEL_COST[model] ?? "—";
  }

  const bothLocal = $derived(
    form.model_analysis.startsWith("ollama/") &&
      form.model_planning.startsWith("ollama/"),
  );

  // ── Load ──────────────────────────────────────────────────────────────
  onMount(async () => {
    const uid = $userId;
    savedFormJson = JSON.stringify(form); // initialise with blank form snapshot
    if (!uid) {
      loading = false;
      return;
    }
    try {
      const [p, s] = await Promise.all([
        getProfile(uid),
        getSchedulerStatus().catch(() => null),
      ]);
      profile = p;
      userProfile.set(p);
      schedulerStatus = s;
      const f = {
        display_name: p.display_name ?? "",
        goal_event: p.goal_event ?? "",
        goal_date: p.goal_date ?? "",
        fitness_level: p.fitness_level ?? "",
        medical_conditions: Array.isArray(p.medical_conditions)
          ? p.medical_conditions.join(", ")
          : ((p.medical_conditions as unknown as string) ?? ""),
        dietary_preference: p.dietary_preference ?? "",
        dietary_allergies: p.dietary_allergies ?? "",
        max_weekly_hours:
          p.max_weekly_hours != null ? String(p.max_weekly_hours) : "",
        date_of_birth: p.date_of_birth ?? "",
        lthr: p.lthr != null ? String(p.lthr) : "",
        garmin_email: p.garmin_email ?? "",
        garmin_password: "",
        swim_equipment: p.swim_equipment ?? "",
        swim_strokes: p.swim_strokes ?? "",
        model_analysis: p.model_analysis ?? "",
        model_planning: p.model_planning ?? "",
      };
      form = { ...f };
      savedFormJson = JSON.stringify(f);
    } catch (e: unknown) {
      showToast(
        e instanceof Error ? e.message : "Failed to load profile",
        "error",
      );
    } finally {
      loading = false;
    }
  });

  // ── Save profile ──────────────────────────────────────────────────────
  async function saveProfile() {
    if (!$userId) return;
    saving = true;
    try {
      const updated = await updateProfile($userId, {
        display_name: form.display_name || null,
        goal_event: form.goal_event || null,
        goal_date: form.goal_date || null,
        fitness_level: form.fitness_level || null,
        medical_conditions: form.medical_conditions
          ? form.medical_conditions
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
        dietary_preference: form.dietary_preference || null,
        dietary_allergies: form.dietary_allergies || null,
        max_weekly_hours: form.max_weekly_hours
          ? parseFloat(form.max_weekly_hours)
          : null,
        garmin_email: form.garmin_email || null,
        ...(form.garmin_password
          ? { garmin_password: form.garmin_password }
          : {}),
        swim_equipment: form.swim_equipment || null,
        swim_strokes: form.swim_strokes || null,
        date_of_birth: form.date_of_birth || null,
        lthr: form.lthr ? parseInt(form.lthr) : null,
        model_analysis: form.model_analysis,
        model_planning: form.model_planning,
      });
      form.garmin_password = "";
      profile = updated;
      userProfile.set(updated);
      savedFormJson = JSON.stringify(form);
      saveSuccess = true;
      showToast("Settings saved");
      setTimeout(() => {
        saveSuccess = false;
      }, 3000);
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Save failed", "error");
    } finally {
      saving = false;
    }
  }

  function discardChanges() {
    form = JSON.parse(savedFormJson);
  }

  // ── Sync / pipeline triggers ──────────────────────────────────────────
  async function handleSyncNow() {
    if (!$userId) return;
    syncTriggering = true;
    try {
      await triggerSync($userId);
      showToast("Sync started — this may take 30-60 seconds");
    } catch {
      showToast("Sync trigger failed", "error");
    }
    setTimeout(() => {
      syncTriggering = false;
    }, 3000);
  }

  async function handlePipelineNow() {
    if (!$userId) return;
    pipelineTriggering = true;
    try {
      await triggerPipeline($userId);
      showToast("Pipeline started — check dashboard in ~2 minutes");
    } catch {
      showToast("Pipeline trigger failed", "error");
    }
    setTimeout(() => {
      pipelineTriggering = false;
    }, 3000);
  }

  // ── Danger zone ───────────────────────────────────────────────────────
  async function handleClearPlan() {
    if (!$userId) return;
    clearPlanLoading = true;
    clearPlanConfirming = false;
    try {
      const res = await clearCurrentPlan($userId);
      currentPlan.set(null);
      addToast(
        res.message ??
          "Training plan cleared. Run pipeline to generate a new one.",
        "success",
      );
    } catch (e: unknown) {
      addToast(
        e instanceof Error ? e.message : "Failed to clear plan",
        "error",
      );
    } finally {
      clearPlanLoading = false;
    }
  }

  async function handleResetAll() {
    if (!$userId || resetTypedWord !== "RESET") return;
    resetLoading = true;
    resetConfirming = false;
    resetTypedWord = "";
    try {
      const result = await resetAllData($userId);
      currentPlan.set(null);
      todayReport.set(null);
      addToast(`Reset complete. ${result.message}`, "success", 8000);
      addToast(
        "Next: Go to Settings → Data & Sync → Sync Garmin Now",
        "info",
        10000,
      );
    } catch (e: unknown) {
      addToast(
        e instanceof Error ? `Reset failed: ${e.message}` : "Reset failed",
        "error",
      );
    } finally {
      resetLoading = false;
    }
  }

  const TODAY = new Date().toISOString().split("T")[0];

  const GOAL_OPTIONS = [
    { value: "", label: "Select your goal..." },
    { value: "ironman_703", label: "Half Ironman (70.3)" },
    { value: "ironman", label: "Full Ironman (140.6)" },
    { value: "marathon", label: "Marathon" },
    { value: "half_marathon", label: "Half Marathon" },
    { value: "olympic_tri", label: "Olympic Triathlon" },
    { value: "sprint_tri", label: "Sprint Triathlon" },
    { value: "custom", label: "Custom" },
  ];

  const DIET_OPTIONS = [
    { value: "omnivore", label: "Omnivore" },
    { value: "vegetarian", label: "Vegetarian" },
    { value: "vegan", label: "Vegan" },
    { value: "vegan-junk", label: "Vegan Junk" },
  ];

  const SWIM_EQUIPMENT_OPTIONS = [
    { value: "pull_buoy", label: "Pull Buoy" },
    { value: "paddles", label: "Paddles" },
    { value: "fins", label: "Fins" },
    { value: "wetsuit", label: "Wetsuit" },
    { value: "kickboard", label: "Kickboard" },
  ];
  const SWIM_STROKES_LIST = [
    "freestyle",
    "breaststroke",
    "backstroke",
    "butterfly",
  ];
  const SWIM_LEVELS = ["learning", "beginner", "intermediate", "expert"];

  function equipmentSet(): Set<string> {
    return new Set(
      form.swim_equipment
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    );
  }
  function toggleEquipment(item: string) {
    const set = equipmentSet();
    if (set.has(item)) set.delete(item);
    else set.add(item);
    form.swim_equipment = [...set].join(",");
  }
  function strokeLevels(): Record<string, string> {
    const map: Record<string, string> = {};
    for (const part of form.swim_strokes
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)) {
      const [stroke, level] = part.split(":");
      if (stroke && level) map[stroke] = level;
    }
    return map;
  }
  function setStrokeLevel(stroke: string, level: string) {
    const map = strokeLevels();
    if (level) map[stroke] = level;
    else delete map[stroke];
    form.swim_strokes = Object.entries(map)
      .map(([k, v]) => `${k}:${v}`)
      .join(",");
  }
</script>

<!-- Toast -->
{#if toast}
  <div
    class="fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg text-sm font-medium animate-slide-in
           {toast.kind === 'success'
      ? 'bg-green-600 text-white'
      : 'bg-red-600 text-white'}"
    role="alert"
  >
    {#if toast.kind === "success"}
      <CheckCircle size={15} class="shrink-0" />
    {:else}
      <AlertCircle size={15} class="shrink-0" />
    {/if}
    {toast.message}
  </div>
{/if}

<div class="max-w-3xl mx-auto py-8 px-4 space-y-6 pb-28">
  <!-- Header -->
  <div>
    <h1 class="text-2xl font-bold text-slate-100">Settings</h1>
    <p class="text-sm text-slate-400 mt-1">
      Manage your profile, AI models, and data sync
    </p>
  </div>

  <!-- ── SECTION 1: Athlete Profile ────────────────────────────────── -->
  <div class="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
    <button
      onclick={() => {
        activeSection = activeSection === "profile" ? "" : "profile";
      }}
      class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-700/40 transition"
    >
      <div class="flex items-center gap-3">
        <User size={18} class="text-blue-400 shrink-0" />
        <span class="font-semibold text-slate-100">Athlete Profile</span>
      </div>
      {#if activeSection === "profile"}
        <ChevronUp size={16} class="text-slate-400" />
      {:else}
        <ChevronDown size={16} class="text-slate-400" />
      {/if}
    </button>

    {#if activeSection === "profile"}
      <div class="px-5 pb-6 border-t border-slate-700 pt-5 space-y-5">
        {#if loading}
          <div class="space-y-3">
            {#each [1, 2, 3, 4] as _}
              <div class="h-10 bg-slate-700 rounded animate-pulse"></div>
            {/each}
          </div>
        {:else}
          <div class="grid sm:grid-cols-2 gap-4">
            <!-- Display Name -->
            <div class="space-y-1">
              <label for="display-name" class="label-sm">Display Name</label>
              <input
                id="display-name"
                type="text"
                bind:value={form.display_name}
                placeholder="Your name"
                class="input-field"
              />
            </div>

            <!-- Goal Event -->
            <div class="space-y-1">
              <label for="goal-event" class="label-sm">Goal Event</label>
              <select
                id="goal-event"
                bind:value={form.goal_event}
                class="input-field"
              >
                {#each GOAL_OPTIONS as opt}
                  <option value={opt.value}>{opt.label}</option>
                {/each}
              </select>
            </div>

            <!-- Goal Date -->
            <div class="space-y-1">
              <label for="goal-date" class="label-sm">Goal Date</label>
              <input
                id="goal-date"
                type="date"
                bind:value={form.goal_date}
                min={TODAY}
                class="input-field"
              />
            </div>

            <!-- Max Weekly Hours -->
            <div class="space-y-1">
              <label for="max-hours" class="label-sm">Max Weekly Hours</label>
              <input
                id="max-hours"
                type="number"
                bind:value={form.max_weekly_hours}
                min="1"
                max="25"
                step="0.5"
                placeholder="e.g. 8"
                class="input-field"
              />
              <p class="text-xs text-slate-500">
                Total hours available per week
              </p>
            </div>

            <!-- Date of Birth -->
            <div class="space-y-1">
              <label for="date-of-birth" class="label-sm">Date of Birth</label>
              <input
                id="date-of-birth"
                type="date"
                bind:value={form.date_of_birth}
                max={TODAY}
                class="input-field"
              />
              <p class="text-xs text-slate-500">
                Used to calculate age-based max HR
              </p>
            </div>

            <!-- LTHR -->
            <div class="space-y-1">
              <label for="lthr" class="label-sm"
                >Lactate Threshold HR (bpm)</label
              >
              <input
                id="lthr"
                type="number"
                bind:value={form.lthr}
                min="100"
                max="220"
                step="1"
                placeholder="e.g. 165"
                class="input-field"
              />
              <p class="text-xs text-slate-500">
                Overrides age formula. Run a 20-min all-out TT and use avg HR.
              </p>
            </div>
          </div>

          <!-- Fitness Level segmented control -->
          <div class="space-y-2">
            <p class="label-sm">Fitness Level</p>
            <div class="flex gap-2">
              {#each ["beginner", "intermediate", "advanced"] as level}
                <button
                  onclick={() => {
                    form.fitness_level = level;
                  }}
                  class="flex-1 py-2 rounded-lg text-sm font-medium capitalize transition-colors border
                         {form.fitness_level === level
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-slate-700 text-slate-300 border-slate-600 hover:bg-slate-600'}"
                  >{level}</button
                >
              {/each}
            </div>
          </div>

          <!-- Medical Conditions -->
          <div class="space-y-1">
            <label for="medical-conditions" class="label-sm"
              >Medical Conditions</label
            >
            <textarea
              id="medical-conditions"
              bind:value={form.medical_conditions}
              rows={2}
              placeholder="e.g. asthma, right knee injury, lower back pain"
              class="input-field resize-none"
            ></textarea>
            <p class="text-xs text-slate-500">
              Separate multiple conditions with commas
            </p>
          </div>

          <!-- Dietary Preference -->
          <div class="space-y-2">
            <p class="label-sm">Dietary Preference</p>
            <div class="flex flex-wrap gap-4">
              {#each DIET_OPTIONS as diet}
                <label
                  class="flex items-center gap-2 text-sm text-slate-300 cursor-pointer"
                >
                  <input
                    type="radio"
                    name="diet"
                    value={diet.value}
                    bind:group={form.dietary_preference}
                    class="accent-blue-500"
                  />
                  {diet.label}
                </label>
              {/each}
            </div>
          </div>

          <!-- Dietary Allergies -->
          <div class="space-y-1">
            <label for="dietary-allergies" class="label-sm"
              >Dietary Allergies</label
            >
            <input
              id="dietary-allergies"
              type="text"
              bind:value={form.dietary_allergies}
              placeholder="e.g. gluten, dairy, nuts"
              class="input-field"
            />
            <p class="text-xs text-slate-500">
              Separate multiple allergies with commas
            </p>
          </div>

          <!-- Swim Equipment -->
          <div class="space-y-2">
            <p class="label-sm">Swim Equipment</p>
            <div class="flex flex-wrap gap-x-4 gap-y-2">
              {#each SWIM_EQUIPMENT_OPTIONS as eq}
                <label
                  class="flex items-center gap-2 text-sm text-slate-300 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={equipmentSet().has(eq.value)}
                    onchange={() => toggleEquipment(eq.value)}
                    class="accent-blue-500"
                  />
                  {eq.label}
                </label>
              {/each}
            </div>
          </div>

          <!-- Swim Strokes -->
          <div class="space-y-2">
            <p class="label-sm">Swim Strokes &amp; Level</p>
            <div class="grid sm:grid-cols-2 gap-2">
              {#each SWIM_STROKES_LIST as stroke}
                <div class="flex items-center gap-2">
                  <span class="text-sm text-slate-300 capitalize w-28 shrink-0"
                    >{stroke}</span
                  >
                  <select
                    value={strokeLevels()[stroke] ?? ""}
                    onchange={(e) =>
                      setStrokeLevel(
                        stroke,
                        (e.target as HTMLSelectElement).value,
                      )}
                    class="input-field py-1.5 text-xs"
                  >
                    <option value="">— None</option>
                    {#each SWIM_LEVELS as lvl}
                      <option value={lvl}
                        >{lvl.charAt(0).toUpperCase() + lvl.slice(1)}</option
                      >
                    {/each}
                  </select>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <!-- ── SECTION 2: AI Models ──────────────────────────────────────── -->
  <div class="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
    <button
      onclick={() => {
        activeSection = activeSection === "models" ? "" : "models";
      }}
      class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-700/40 transition"
    >
      <div class="flex items-center gap-3">
        <Brain size={18} class="text-purple-400 shrink-0" />
        <span class="font-semibold text-slate-100">AI Models</span>
      </div>
      {#if activeSection === "models"}
        <ChevronUp size={16} class="text-slate-400" />
      {:else}
        <ChevronDown size={16} class="text-slate-400" />
      {/if}
    </button>

    {#if activeSection === "models"}
      <div class="px-5 pb-6 border-t border-slate-700 pt-5 space-y-5">
        <!-- Info box -->
        <div
          class="flex gap-2 bg-blue-900/30 border border-blue-800/50 rounded-lg p-3 text-xs text-blue-300"
        >
          <Info size={14} class="shrink-0 mt-0.5" />
          <span
            >Models are called via OpenRouter (cloud) or Ollama (local). Format: <code
              class="font-mono">openrouter/provider/model-name</code
            >
            or <code class="font-mono">ollama/model-name</code></span
          >
        </div>

        <!-- Analysis model -->
        <div class="space-y-1.5">
          <div class="flex items-center gap-2">
            <label for="model-analysis" class="label-sm">Analysis Agent</label>
            <span
              class="text-xs text-slate-500"
              title="Analyses your wearable data and generates readiness reports"
            >
              ⓘ Analyses wearable data → readiness reports
            </span>
          </div>
          <select
            id="model-analysis"
            bind:value={form.model_analysis}
            class="input-field"
          >
            <optgroup label="☁️ OpenRouter (Cloud)">
              <option value="openrouter/anthropic/claude-3-5-sonnet-20241022"
                >Claude 3.5 Sonnet (Best quality)</option
              >
              <option value="openrouter/anthropic/claude-3-haiku-20240307"
                >Claude 3 Haiku (Fast + cheap)</option
              >
              <option value="openrouter/google/gemini-flash-1.5"
                >Gemini Flash 1.5 (Very cheap)</option
              >
              <option value="openrouter/meta-llama/llama-3.1-70b-instruct"
                >Llama 3.1 70B (Open source)</option
              >
            </optgroup>
            <optgroup label="🖥️ Ollama (Local - Free)">
              <option value="ollama/llama3.2:3b"
                >Llama 3.2 3B (Fast, low quality)</option
              >
              <option value="ollama/llama3.3:70b"
                >Llama 3.3 70B (Slow, high quality)</option
              >
              <option value="ollama/qwen2.5:32b"
                >Qwen 2.5 32B (Good balance)</option
              >
              <option value="ollama/mistral-nemo">Mistral Nemo (Fast)</option>
            </optgroup>
          </select>
        </div>

        <!-- Planning model -->
        <div class="space-y-1.5">
          <div class="flex items-center gap-2">
            <label for="model-planning" class="label-sm">Planning Agent</label>
            <span class="text-xs text-slate-500"
              >ⓘ Generates your 14-day training plan</span
            >
          </div>
          <select
            id="model-planning"
            bind:value={form.model_planning}
            class="input-field"
          >
            <optgroup label="☁️ OpenRouter (Cloud)">
              <option value="openrouter/anthropic/claude-3-5-sonnet-20241022"
                >Claude 3.5 Sonnet (Best quality)</option
              >
              <option value="openrouter/anthropic/claude-3-haiku-20240307"
                >Claude 3 Haiku (Fast + cheap)</option
              >
              <option value="openrouter/google/gemini-flash-1.5"
                >Gemini Flash 1.5 (Very cheap)</option
              >
              <option value="openrouter/meta-llama/llama-3.1-70b-instruct"
                >Llama 3.1 70B (Open source)</option
              >
            </optgroup>
            <optgroup label="🖥️ Ollama (Local - Free)">
              <option value="ollama/llama3.2:3b"
                >Llama 3.2 3B (Fast, low quality)</option
              >
              <option value="ollama/llama3.3:70b"
                >Llama 3.3 70B (Slow, high quality)</option
              >
              <option value="ollama/qwen2.5:32b"
                >Qwen 2.5 32B (Good balance)</option
              >
              <option value="ollama/mistral-nemo">Mistral Nemo (Fast)</option>
            </optgroup>
          </select>
        </div>

        <!-- Cost estimate -->
        <div
          class="bg-slate-700/50 rounded-lg p-3 text-xs text-slate-400 space-y-1"
        >
          {#if bothLocal}
            <p class="text-green-400 font-medium">
              ✓ Zero API cost — running fully local
            </p>
          {:else}
            <p class="font-medium text-slate-300">Estimated cost per day:</p>
            <p>
              Analysis: <span class="text-slate-200"
                >{modelCostLabel(form.model_analysis)}</span
              >
            </p>
            <p>
              Planning: <span class="text-slate-200"
                >{modelCostLabel(form.model_planning)}</span
              >
            </p>
          {/if}
        </div>

        <!-- Context transfer warning -->
        {#if modelChanged}
          <div
            class="flex gap-2 bg-amber-900/30 border border-amber-700/50 rounded-lg p-3 text-xs text-amber-300"
          >
            <AlertCircle size={14} class="shrink-0 mt-0.5" />
            <span
              >⚠️ Changing models will trigger a context transfer on next
              pipeline run. Prior analysis context will be injected into the new
              model's prompt.</span
            >
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <!-- ── SECTION 3: Data & Sync ─────────────────────────────────────── -->
  <div class="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
    <button
      onclick={() => {
        activeSection = activeSection === "sync" ? "" : "sync";
      }}
      class="w-full flex items-center justify-between p-5 text-left hover:bg-slate-700/40 transition"
    >
      <div class="flex items-center gap-3">
        <RefreshCw size={18} class="text-green-400 shrink-0" />
        <span class="font-semibold text-slate-100">Data &amp; Sync</span>
      </div>
      {#if activeSection === "sync"}
        <ChevronUp size={16} class="text-slate-400" />
      {:else}
        <ChevronDown size={16} class="text-slate-400" />
      {/if}
    </button>

    {#if activeSection === "sync"}
      <div class="px-5 pb-6 border-t border-slate-700 pt-5 space-y-5">
        <!-- Scheduler status -->
        <div class="bg-slate-700/50 rounded-lg p-4 space-y-3">
          <div class="flex items-center justify-between">
            <p class="text-sm font-medium text-slate-200">Nightly Scheduler</p>
            {#if schedulerStatus?.is_running}
              <span
                class="inline-flex items-center gap-1.5 text-xs font-medium text-green-400 bg-green-900/30 border border-green-800/50 px-2 py-0.5 rounded-full"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-green-400"
                ></span>Active
              </span>
            {:else}
              <span
                class="inline-flex items-center gap-1.5 text-xs font-medium text-red-400 bg-red-900/30 border border-red-800/50 px-2 py-0.5 rounded-full"
              >
                <span class="w-1.5 h-1.5 rounded-full bg-red-400"
                ></span>Inactive
              </span>
            {/if}
          </div>
          {#if schedulerStatus?.jobs}
            <div class="space-y-1.5 text-xs text-slate-400">
              {#each schedulerStatus.jobs as job}
                <div class="flex justify-between">
                  <span
                    >{job.id === "garmin_sync"
                      ? "🔄 Garmin Sync"
                      : "🤖 AI Pipeline"}</span
                  >
                  <span class="text-slate-300">
                    {job.next_run
                      ? new Date(job.next_run).toLocaleString()
                      : "—"}
                  </span>
                </div>
              {/each}
            </div>
          {:else}
            <p class="text-xs text-slate-500">
              🔄 Garmin Sync — 03:00 UTC daily
            </p>
            <p class="text-xs text-slate-500">
              🤖 AI Pipeline — 06:00 UTC daily
            </p>
          {/if}
        </div>

        <!-- Garmin Credentials -->
        <div class="space-y-2">
          <p class="label-sm">Garmin Account</p>
          <div class="grid sm:grid-cols-2 gap-3">
            <div class="space-y-1">
              <label for="garmin-email" class="text-xs text-slate-400"
                >Email</label
              >
              <input
                id="garmin-email"
                type="email"
                bind:value={form.garmin_email}
                placeholder="your@garmin.com"
                class="input-field"
                autocomplete="username"
              />
            </div>
            <div class="space-y-1">
              <label for="garmin-password" class="text-xs text-slate-400"
                >Password</label
              >
              <input
                id="garmin-password"
                type="password"
                bind:value={form.garmin_password}
                placeholder="Leave blank to keep current"
                class="input-field"
                autocomplete="current-password"
              />
            </div>
          </div>
          <p class="text-xs text-slate-500">
            Used only for Garmin Connect sync. Stored locally.
          </p>
        </div>

        <!-- Manual triggers -->
        <div class="flex flex-wrap gap-3">
          <button
            onclick={handleSyncNow}
            disabled={syncTriggering}
            class="flex items-center gap-2 px-4 py-2 bg-slate-700 border border-slate-600 hover:bg-slate-600 text-slate-200 text-sm rounded-lg transition disabled:opacity-60"
          >
            <RefreshCw size={14} class={syncTriggering ? "animate-spin" : ""} />
            {syncTriggering ? "Syncing…" : "Sync Garmin Now"}
          </button>
          <button
            onclick={handlePipelineNow}
            disabled={pipelineTriggering}
            class="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition disabled:opacity-60"
          >
            <Zap size={14} />
            {pipelineTriggering ? "Starting…" : "Run AI Pipeline"}
          </button>
        </div>
        <p class="text-xs text-slate-500">
          These run automatically each morning. Use manual triggers to refresh
          now.
        </p>
      </div>
    {/if}
  </div>

  <!-- ── SECTION 4: Danger Zone ─────────────────────────────────────── -->
  <div class="bg-slate-800 border border-red-900/50 rounded-xl overflow-hidden">
    <button
      onclick={() => {
        activeSection = activeSection === "danger" ? "" : "danger";
      }}
      class="w-full flex items-center justify-between p-5 text-left hover:bg-red-900/10 transition"
    >
      <div class="flex items-center gap-3">
        <AlertCircle size={18} class="text-red-400 shrink-0" />
        <span class="font-semibold text-red-400">Danger Zone</span>
      </div>
      {#if activeSection === "danger"}
        <ChevronUp size={16} class="text-slate-400" />
      {:else}
        <ChevronDown size={16} class="text-slate-400" />
      {/if}
    </button>

    {#if activeSection === "danger"}
      <div class="px-5 pb-6 border-t border-red-900/40 pt-5 space-y-5">
        <!-- ── Clear Training Plan ────────────────────────── -->
        <div
          class="bg-red-900/20 border border-red-800/50 rounded-xl p-5 space-y-3"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="space-y-1 min-w-0">
              <p class="text-sm font-medium text-slate-100">
                Clear Training Plan
              </p>
              <p class="text-xs text-slate-400">
                Removes your current plan. Your wearable data and history are
                kept. A new plan will be generated on the next pipeline run.
              </p>
              <p class="text-xs text-slate-500 italic">
                This is reversible — just run the pipeline again.
              </p>
            </div>
            <button
              onclick={() => {
                clearPlanConfirming = true;
              }}
              disabled={clearPlanLoading}
              class="shrink-0 px-4 py-2 text-sm border border-red-500/60 text-red-400
                     hover:bg-red-900/30 rounded-lg transition
                     disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {#if clearPlanLoading}
                <span
                  class="w-3.5 h-3.5 border-2 border-red-400/40 border-t-red-400 rounded-full animate-spin"
                ></span>
                Clearing…
              {:else}
                Clear Plan
              {/if}
            </button>
          </div>

          {#if clearPlanConfirming}
            <div
              class="bg-amber-900/20 border border-amber-700/40 rounded-lg p-3 space-y-3"
            >
              <p class="text-xs text-amber-300">
                ⚠️ This will deactivate your current 14-day plan.
              </p>
              <div class="flex gap-2">
                <button
                  onclick={() => {
                    clearPlanConfirming = false;
                  }}
                  class="px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition"
                  >Cancel</button
                >
                <button
                  onclick={handleClearPlan}
                  class="px-3 py-1.5 text-xs bg-red-600 hover:bg-red-700 text-white rounded-lg transition"
                  >Yes, Clear Plan</button
                >
              </div>
            </div>
          {/if}
        </div>

        <!-- ── Reset All Data ─────────────────────────────── -->
        <div
          class="bg-red-900/25 border border-red-700/50 border-t-2 border-t-red-500 rounded-xl p-5 space-y-3"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="space-y-1 min-w-0">
              <p
                class="text-sm font-medium text-red-300 flex items-center gap-1.5"
              >
                <AlertTriangle size={14} class="shrink-0" />
                Reset All Data
              </p>
              <p class="text-xs text-slate-400">
                Permanently deletes all wearable data, training plans, readiness
                reports, check-ins, and AI context. Your account and profile
                settings are kept.
              </p>
              <p class="text-xs font-semibold text-red-400">
                ⚠️ This cannot be undone.
              </p>
            </div>
            <button
              onclick={() => {
                resetConfirming = true;
              }}
              disabled={resetLoading}
              class="shrink-0 px-4 py-2 text-sm bg-red-600 hover:bg-red-700 text-white
                     rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed
                     flex items-center gap-2"
            >
              {#if resetLoading}
                <span
                  class="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin"
                ></span>
                Resetting…
              {:else}
                Reset All Data
              {/if}
            </button>
          </div>

          {#if resetConfirming}
            <div
              class="bg-red-950/50 border border-red-700/50 rounded-lg p-4 space-y-4"
            >
              <!-- Checklist -->
              <div class="space-y-1.5 text-xs">
                <p class="font-medium text-slate-300 mb-2">
                  What will be deleted:
                </p>
                {#each [{ deleted: true, label: "All Garmin sync data" }, { deleted: true, label: "All training plans" }, { deleted: true, label: "All readiness reports" }, { deleted: true, label: "All check-ins and feedback" }, { deleted: true, label: "AI agent context (model memory)" }, { deleted: true, label: "Job history" }, { deleted: false, label: "Your profile and settings (kept)" }, { deleted: false, label: "Your account (kept)" }] as item}
                  <div class="flex items-center gap-2">
                    {#if item.deleted}
                      <span class="text-red-400 font-bold w-3 text-center"
                        >✗</span
                      >
                      <span class="text-slate-300">{item.label}</span>
                    {:else}
                      <span class="text-green-400 font-bold w-3 text-center"
                        >✓</span
                      >
                      <span class="text-slate-500">{item.label}</span>
                    {/if}
                  </div>
                {/each}
              </div>

              <!-- Type to confirm -->
              <div class="space-y-1.5">
                <label for="reset-confirm-input" class="text-xs text-slate-400">
                  Type <span class="font-mono font-bold text-red-400"
                    >RESET</span
                  > to confirm
                </label>
                <input
                  id="reset-confirm-input"
                  type="text"
                  value={resetTypedWord}
                  oninput={(e) => {
                    resetTypedWord = (e.target as HTMLInputElement).value
                      .trim()
                      .toUpperCase();
                  }}
                  placeholder="Type RESET here"
                  class="input-field text-sm"
                />
              </div>

              <!-- Actions -->
              <div class="flex gap-2">
                <button
                  onclick={() => {
                    resetConfirming = false;
                    resetTypedWord = "";
                  }}
                  class="px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition"
                  >Cancel</button
                >
                <button
                  onclick={handleResetAll}
                  disabled={resetTypedWord !== "RESET"}
                  class="px-3 py-1.5 text-xs bg-red-600 hover:bg-red-700 text-white rounded-lg transition
                         disabled:opacity-50 disabled:cursor-not-allowed"
                  >Permanently Delete All Data</button
                >
              </div>
            </div>
          {/if}

          {#if resetLoading}
            <div
              class="bg-red-900/20 rounded-lg px-4 py-2 flex items-center gap-2 text-xs text-red-300 animate-pulse"
            >
              <span
                class="w-3 h-3 border-2 border-red-400/40 border-t-red-400 rounded-full animate-spin"
              ></span>
              Deleting data…
            </div>
          {/if}
        </div>
      </div>
    {/if}
  </div>
</div>

<!-- Sticky save bar -->
{#if isDirty}
  <div
    class="fixed bottom-16 md:bottom-0 left-0 right-0 z-40 bg-slate-900/95 backdrop-blur border-t border-slate-700 px-4 py-3"
  >
    <div class="max-w-3xl mx-auto flex items-center justify-between gap-4">
      <p class="text-sm text-slate-300">You have unsaved changes</p>
      <div class="flex gap-2">
        <button
          onclick={discardChanges}
          class="px-4 py-2 text-sm bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition"
          >Discard</button
        >
        <button
          onclick={saveProfile}
          disabled={saving}
          class="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition disabled:opacity-60"
        >
          {#if saving}
            <span
              class="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin"
            ></span>
            Saving…
          {:else if saveSuccess}
            <CheckCircle size={14} />
            Saved!
          {:else}
            <Save size={14} />
            Save Changes
          {/if}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  :global(.label-sm) {
    display: block;
    font-size: 0.75rem;
    font-weight: 600;
    color: rgb(148 163 184);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  :global(.input-field) {
    width: 100%;
    border-radius: 0.5rem;
    border: 1px solid rgb(71 85 105);
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
    color: rgb(226 232 240);
    background-color: rgb(51 65 85);
    outline: none;
  }
  :global(.input-field:focus) {
    border-color: rgb(96 165 250);
    box-shadow: 0 0 0 2px rgb(96 165 250 / 0.3);
  }
  @keyframes slide-in {
    from {
      opacity: 0;
      transform: translateX(12px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }
  .animate-slide-in {
    animation: slide-in 0.2s ease-out both;
  }
</style>
