<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { Chart, registerables } from "chart.js";

  Chart.register(...registerables);

  export interface BarDataset {
    label: string;
    data: number[];
    color: string;
  }

  interface Props {
    labels: string[];
    datasets: BarDataset[];
    height?: number;
    stacked?: boolean;
    unit?: string;
  }

  let {
    labels,
    datasets,
    height = 180,
    stacked = true,
    unit = "min",
  }: Props = $props();

  let canvas: HTMLCanvasElement;
  let chart: Chart | null = null;

  function buildDatasets() {
    return datasets.map((ds) => ({
      label: ds.label,
      data: [...ds.data],
      backgroundColor: ds.color,
      borderColor: ds.color,
      borderWidth: 0,
      borderRadius: 4,
    }));
  }

  onMount(() => {
    chart = new Chart(canvas, {
      type: "bar",
      data: {
        labels: [...labels],
        datasets: buildDatasets(),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: "top",
            labels: { boxWidth: 12, font: { size: 11 } },
          },
          tooltip: {
            mode: "index",
            intersect: false,
            callbacks: {
              label: (ctx) =>
                `${ctx.dataset.label}: ${ctx.parsed.y != null ? ctx.parsed.y.toFixed(0) : "—"}${unit}`,
            },
          },
        },
        scales: {
          x: {
            stacked,
            grid: { display: false },
            ticks: { font: { size: 10 } },
          },
          y: {
            stacked,
            grid: { color: "#334155" },
            ticks: {
              font: { size: 10 },
              callback: (v) => `${v}${unit}`,
            },
          },
        },
        interaction: {
          mode: "index",
          intersect: false,
        },
      },
    });
  });

  onDestroy(() => {
    chart?.destroy();
  });

  $effect(() => {
    if (!chart) return;
    chart.data.labels = [...labels];
    chart.data.datasets = buildDatasets();
    chart.update();
  });
</script>

<div style="height: {height}px; position: relative;">
  <canvas bind:this={canvas}></canvas>
</div>
