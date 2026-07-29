export type AnalysisJobStatus =
  | "queued"
  | "segmenting"
  | "skeletonizing"
  | "complete"
  | "failed";

export function hasPositiveNumericValue(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

export function formatVoxelSize(context: {
  scaleUnit: "micron" | "voxel";
  voxelSizeMicron: string;
}) {
  if (context.scaleUnit === "micron" && hasPositiveNumericValue(context.voxelSizeMicron)) {
    return `${context.voxelSizeMicron} micron`;
  }

  return "Unknown; distances remain in pixels/voxels";
}

export function formatAnalysisStatus(status: AnalysisJobStatus | null) {
  if (!status) {
    return "Waiting for analysis job";
  }

  return {
    queued: "Queued",
    segmenting: "Segmenting",
    skeletonizing: "Skeletonizing",
    complete: "Complete",
    failed: "Failed",
  }[status];
}
