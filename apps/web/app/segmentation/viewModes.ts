export type PrimaryViewMode = "original" | "segmentation" | "skeleton" | "defects";
export type SegmentationComparisonMode = "overlay" | "mask";

export const primaryViewModes: {
  id: PrimaryViewMode;
  label: string;
}[] = [
  { id: "original", label: "Original" },
  { id: "segmentation", label: "Segmentation" },
  { id: "skeleton", label: "Skeleton" },
  { id: "defects", label: "Defects" },
];

export const segmentationComparisonModes: {
  id: SegmentationComparisonMode;
  label: string;
}[] = [
  { id: "overlay", label: "Overlay" },
  { id: "mask", label: "Mask" },
];

export function getSliceFetchView(
  viewMode: PrimaryViewMode,
  comparisonMode: SegmentationComparisonMode = "mask",
): "original" | "segmentation" | "skeleton" | null {
  if (viewMode === "defects") {
    return null;
  }

  if (viewMode === "segmentation" && comparisonMode === "overlay") {
    return "original";
  }

  return viewMode;
}

export function getDefectsEmptyStateMessage() {
  return "Defect visualization is unavailable until the defect-detection agent runs.";
}
