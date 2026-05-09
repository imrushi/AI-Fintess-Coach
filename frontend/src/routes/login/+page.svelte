<script lang="ts">
  import { goto } from "$app/navigation";
  import { loginByEmail, storeUserId } from "$lib/api";
  import { userId } from "$lib/stores";

  let email = $state("");
  let loading = $state(false);
  let error = $state<string | null>(null);

  async function handleLogin(e: Event) {
    e.preventDefault();
    const trimmed = email.trim().toLowerCase();
    if (!trimmed) return;
    loading = true;
    error = null;
    try {
      const res = await loginByEmail(trimmed);
      storeUserId(res.user_id);
      userId.set(res.user_id);
      await goto("/");
    } catch (err: unknown) {
      error =
        err instanceof Error ? err.message : "Login failed. Check your email.";
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Login — FitCoach AI</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center bg-slate-900 px-4">
  <div class="w-full max-w-sm space-y-6">
    <!-- Logo / header -->
    <div class="text-center space-y-2">
      <div class="text-5xl">🏃</div>
      <h1 class="text-2xl font-bold text-slate-100">FitCoach AI</h1>
      <p class="text-slate-400 text-sm">
        Enter your email to access your dashboard
      </p>
    </div>

    <!-- Login form -->
    <form
      onsubmit={handleLogin}
      class="bg-slate-800 border border-slate-700 rounded-2xl p-6 space-y-4"
    >
      <div class="space-y-1.5">
        <label for="email" class="block text-sm font-medium text-slate-300">
          Email address
        </label>
        <input
          id="email"
          type="email"
          bind:value={email}
          placeholder="you@example.com"
          autocomplete="email"
          required
          disabled={loading}
          class="w-full rounded-lg border border-slate-600 bg-slate-700 px-3.5 py-2.5
                 text-sm text-slate-100 placeholder:text-slate-500
                 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                 disabled:opacity-50 transition"
        />
      </div>

      {#if error}
        <p
          class="text-sm text-red-400 bg-red-900/20 border border-red-800/50 rounded-lg px-3 py-2"
        >
          {error}
        </p>
      {/if}

      <button
        type="submit"
        disabled={loading || !email.trim()}
        class="w-full py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm
               disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center justify-center gap-2"
      >
        {#if loading}
          <span
            class="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin"
          ></span>
          Signing in…
        {:else}
          Sign in
        {/if}
      </button>
    </form>

    <p class="text-center text-xs text-slate-500">
      Personal coaching dashboard — no password required
    </p>
  </div>
</div>
