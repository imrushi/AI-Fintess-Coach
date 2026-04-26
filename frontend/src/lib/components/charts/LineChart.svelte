<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { Chart, registerables } from "chart.js";

  Chart.register(...registerables);

  export interface ChartDataset {
    label: string;
    data: (number | null)[];
    color: string;
    dashed?: boolean;
  }

  interface Props {
    labels: string[];
    datasets: ChartDataset[];
    height?: number;
    showLegend?: boolean;
    yMin?: number;
    yMax?: number;
    unit?: string;
    fillArea?: boolean;
  }

  let {
    labels,
    datasets,
    height = 200,
    showLegend = true,
    yMin = undefined,
    yMax = undefined,
    unit = "",
    fillArea = false,
  }: Props = $props();

  let canvas: HTMLCanvasElement;
  let chart: Chart | null = null;

  function formatLabel(l: string): string {
    return new Date(l + "T00:00:00").toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  }

  function buildDatasets() {
    return datasets.map((ds) => ({
      label: ds.label,
      data: [...ds.data],
      borderColor: ds.color,
      backgroundColor: fillArea ? ds.color + "20" : "transparent",
      fill: fillArea,
      tension: 0.4,
      pointRadius: 3,
      pointHoverRadius: 5,
      borderDash: ds.dashed ? [5, 5] : [],
      spanGaps: true,
    }));
  }

  onMount(() => {
    chart = new Chart(canvas, {
      type: "line",
      data: {
        labels: [...labels].map(formatLabel),
        datasets: buildDatasets(),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: showLegend,
            position: "top",
            labels: { boxWidth: 12, font: { size: 11 } },
          },
          tooltip: {
            mode: "index",
            intersect: false,
            callbacks: {
              label: (ctx) =>
                `${ctx.dataset.label}: ${ctx.parsed.y != null ? ctx.parsed.y.toFixed(1) : "—"}${unit}`,
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { font: { size: 10 }, maxTicksLimit: 7 },
          },
          y: {
            min: yMin,
            max: yMax,
            grid: { color: "#334155" },
            ticks: {
              font: { size: 10 },
              callback: (v) => `${v}${unit}`,
            },
          },
        },
        interaction: {
          mode: "nearest",
          axis: "x",
          intersect: false,
        },
      },
    });
  });

  onDestroy(() => {
    chart?.destroy();
  });

  // Reactively update when data changes
  $effect(() => {
    if (!chart) return;
    chart.data.labels = [...labels].map(formatLabel);
    chart.data.datasets = buildDatasets();
    chart.update();
  });
</script>

<div style="height: {height}px; position: relative;">
  <canvas bind:this={canvas}></canvas>
</div>
