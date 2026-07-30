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

export type DefectDetectionStatus = "not_run" | "running" | "complete" | "failed";

export function getDefectDetectionStateCopy(
  status: DefectDetectionStatus,
  detail?: string | null,
) {
  if (status === "running") {
    return {
      title: "Defect detection running",
      message: detail ?? "The Defect Detection Agent is analyzing persisted artifacts.",
    };
  }

  if (status === "failed") {
    return {
      title: "Defect detection failed",
      message: detail ?? "Review the backend job error and rerun after fixing inputs.",
    };
  }

  if (status === "complete") {
    return {
      title: "No defects were found",
      message: detail ?? "The completed defect artifact contains no flagged categories.",
    };
  }

  return {
    title: "Defect detection not run",
    message:
      detail ??
      "Run the Defect Detection Agent after segmentation and skeletonization complete.",
  };
}
