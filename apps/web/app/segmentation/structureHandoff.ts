export type StructureHandoffContext = {
  datasetId: string | null;
  scaleUnit: "micron" | "voxel";
  voxelSizeMicron: string;
};

export type StructureHandoffResult = {
  threshold: number;
  foreground_voxel_count: number;
  background_voxel_count: number;
};

export function buildStructureAnalysisHref(
  context: StructureHandoffContext,
  result: StructureHandoffResult | null,
  existingParams?: URLSearchParams | ReadonlyURLSearchParams,
) {
  if (!context.datasetId || !result) {
    return null;
  }

  const params = new URLSearchParams(existingParams?.toString());
  params.set("datasetId", context.datasetId);
  params.set("scaleUnit", context.scaleUnit);
  params.set("threshold", String(result.threshold));
  params.set("foregroundVoxelCount", String(result.foreground_voxel_count));
  params.set("backgroundVoxelCount", String(result.background_voxel_count));

  if (context.scaleUnit === "micron" && Number(context.voxelSizeMicron) > 0) {
    params.set("voxelSizeMicron", context.voxelSizeMicron);
  } else {
    params.delete("voxelSizeMicron");
  }

  return `/structure-analysis?${params.toString()}`;
}

type ReadonlyURLSearchParams = {
  toString: () => string;
};
