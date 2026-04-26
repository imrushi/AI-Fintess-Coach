<script lang="ts">
  interface Props {
    value?: number;
    label?: string;
    sublabel?: string;
    size?: number;
    color?: string;
    showValue?: boolean;
  }

  let {
    value = 0,
    label = "",
    sublabel = "",
    size = 120,
    color = "#3b82f6",
    showValue = true,
  }: Props = $props();

  const cx = $derived(size / 2);
  const cy = $derived(size / 2);
  const radius = $derived(size * 0.38);
  const circumference = $derived(2 * Math.PI * radius);
  const strokeWidth = $derived(size * 0.1);
  const clamped = $derived(Math.min(100, Math.max(0, value)));
  const strokeDashoffset = $derived(
    circumference - (clamped / 100) * circumference,
  );
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 {size} {size}"
  role="img"
  aria-label="{label}: {Math.round(value)}"
>
  <!-- Background track -->
  <circle
    {cx}
    {cy}
    r={radius}
    fill="none"
    stroke="#334155"
    stroke-width={strokeWidth}
  />
  <!-- Value arc -->
  <circle
    {cx}
    {cy}
    r={radius}
    fill="none"
    stroke={color}
    stroke-width={strokeWidth}
    stroke-linecap="round"
    stroke-dasharray={circumference}
    stroke-dashoffset={strokeDashoffset}
    transform="rotate(-90 {cx} {cy})"
    style="transition: stroke-dashoffset 0.6s ease;"
  />
  {#if showValue}
    <!-- Numeric value -->
    <text
      x={cx}
      y={cy - size * 0.06}
      text-anchor="middle"
      dominant-baseline="middle"
      font-size={size * 0.22}
      font-weight="bold"
      fill="#f8fafc">{Math.round(value)}</text
    >
    <!-- Label -->
    <text
      x={cx}
      y={cy + size * 0.15}
      text-anchor="middle"
      dominant-baseline="middle"
      font-size={size * 0.11}
      fill="#94a3b8">{label}</text
    >
    {#if sublabel}
      <!-- Sublabel -->
      <text
        x={cx}
        y={cy + size * 0.27}
        text-anchor="middle"
        dominant-baseline="middle"
        font-size={size * 0.1}
        font-weight="500"
        fill={color}>{sublabel}</text
      >
    {/if}
  {/if}
</svg>
