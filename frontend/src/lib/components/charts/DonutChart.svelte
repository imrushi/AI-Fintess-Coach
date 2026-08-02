<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { Chart, registerables } from "chart.js";

  Chart.register(...registerables);

  interface Props {
    labels: string[];
    data: number[];
    colors: string[];
    height?: number;
    centerLabel?: string;
  }

  let {
    labels,
    data,
    colors,
    height = 220,
    centerLabel = "",
  }: Props = $props();

  let canvas: HTMLCanvasElement;
  let chart: Chart | null = null;

  const centerTextPlugin = {
    id: "donutCenterText",
    afterDraw(c: Chart) {
      if (!centerLabel) return;
      const { ctx, chartArea } = c;
      const cx = (chartArea.left + chartArea.right) / 2;
      const cy = (chartArea.top + chartArea.bottom) / 2;
      ctx.save();
      ctx.font = "bold 13px sans-serif";
      ctx.fillStyle = "#f8fafc";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(centerLabel, cx, cy);
      ctx.restore();
    },
  };

  onMount(() => {
    const config = {
      type: "doughnut" as const,
      data: {
        labels: [...labels],
        datasets: [
          {
            data: [...data],
            backgroundColor: [...colors],
            borderColor: "#1e293b",
            borderWidth: 2,
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "65%",
        plugins: {
          legend: {
            display: true,
            position: "right",
            labels: {
              boxWidth: 10,
              font: { size: 11 },
              color: "#cbd5e1",
            },
          },
          tooltip: {
            callbacks: {
              label: (ctx: any) => {
                const vals = ctx.dataset.data as number[];
                const total = vals.reduce((a, b) => a + (b as number), 0);
                const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : "0";
                const mins = Math.round(ctx.parsed / 60);
                return `${ctx.label?.split("·")[0].trim()}: ${mins}min (${pct}%)`;
              },
            },
          },
        },
      },
      plugins: [centerTextPlugin],
    };
    chart = new Chart(canvas, config as any);
  });

  onDestroy(() => {
    chart?.destroy();
  });

  $effect(() => {
    if (!chart) return;
    chart.data.labels = [...labels];
    chart.data.datasets[0].data = [...data];
    (chart.data.datasets[0] as any).backgroundColor = [...colors];
    chart.update();
  });
</script>

<div style="height: {height}px; position: relative;">
  <canvas bind:this={canvas}></canvas>
</div>
