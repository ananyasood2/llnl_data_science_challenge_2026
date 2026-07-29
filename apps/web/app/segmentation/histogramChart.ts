export type HistogramScope = "volume" | "slice";

export type HistogramPayload = {
  dataset_id: string;
  scope: HistogramScope;
  axis: "x" | "y" | "z" | null;
  index: number | null;
  bin_edges: number[];
  bin_counts: number[];
  threshold: number;
  foreground_voxel_count: number;
  background_voxel_count: number;
  foreground_percentage: number;
  background_percentage: number;
};

export function clampUnitInterval(value: number) {
  if (!Number.isFinite(value)) {
    return 0;
  }

  return Math.min(1, Math.max(0, value));
}

export function getThresholdPercent(threshold: number) {
  return clampUnitInterval(threshold) * 100;
}

export function getHistogramPath(counts: number[], width: number, height: number) {
  if (!counts.length) {
    return "";
  }

  const maxCount = Math.max(...counts, 1);
  const points = counts.map((count, index) => {
    const x = counts.length === 1 ? width : ((index + 1) / counts.length) * width;
    const y = height - (count / maxCount) * height;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return `M0,${height} L0,${height} L${points.join(" L")} L${width},${height} Z`;
}

export function formatVoxelCount(value: number | null) {
  if (value === null || !Number.isFinite(value)) {
    return "Pending";
  }

  return new Intl.NumberFormat("en-US").format(value);
}

export function formatPercent(value: number | null) {
  if (value === null || !Number.isFinite(value)) {
    return "Pending";
  }

  return `${value.toFixed(2)}%`;
}

