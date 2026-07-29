export type HistogramScope = "volume" | "slice";
export type HistogramScale = "linear" | "log";

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
  return getScaledHistogramPath(counts, width, height, "linear");
}

export function getHistogramDisplayCounts(counts: number[], scale: HistogramScale) {
  if (scale === "linear") {
    return counts;
  }

  return counts.map((count) => (count > 0 ? Math.log10(count + 1) : 0));
}

export function getScaledHistogramPath(
  counts: number[],
  width: number,
  height: number,
  scale: HistogramScale,
) {
  if (!counts.length) {
    return "";
  }

  const displayCounts = getHistogramDisplayCounts(counts, scale);
  const maxCount = Math.max(...displayCounts, 1);
  const points = displayCounts.map((count, index) => {
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

export function getSegmentationQualityWarnings(histogram: HistogramPayload | null) {
  if (!histogram) {
    return [];
  }

  const warnings: string[] = [];
  const foregroundPercentage = histogram.foreground_percentage;
  const totalVoxels =
    histogram.foreground_voxel_count + histogram.background_voxel_count;

  if (foregroundPercentage <= 0.1) {
    warnings.push("Foreground is below 0.1%; threshold may be missing material.");
  } else if (foregroundPercentage >= 60) {
    warnings.push("Foreground is above 60%; threshold may be including background.");
  }

  if (totalVoxels > 0 && histogram.bin_counts.length > 0) {
    const thresholdBin = histogram.bin_edges.findIndex((edge, index, edges) => {
      const nextEdge = edges[index + 1];
      return nextEdge !== undefined && histogram.threshold >= edge && histogram.threshold < nextEdge;
    });
    const safeThresholdBin =
      thresholdBin === -1 ? histogram.bin_counts.length - 1 : thresholdBin;
    const nearbyCount = [
      histogram.bin_counts[safeThresholdBin - 1] ?? 0,
      histogram.bin_counts[safeThresholdBin] ?? 0,
      histogram.bin_counts[safeThresholdBin + 1] ?? 0,
    ].reduce((sum, count) => sum + count, 0);
    const nearbyPercentage = (nearbyCount / totalVoxels) * 100;

    if (nearbyPercentage >= 5) {
      warnings.push(
        "Threshold is sensitive; nearby histogram bins contain at least 5% of voxels.",
      );
    }
  }

  return warnings;
}
