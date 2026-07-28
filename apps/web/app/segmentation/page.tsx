import {
  DatasetContext,
  SegmentationClient,
} from "./SegmentationClient";

type SegmentationPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function getParam(
  params: Record<string, string | string[] | undefined>,
  key: string,
  fallback: string,
) {
  const value = params[key];

  if (Array.isArray(value)) {
    return value[0] ?? fallback;
  }

  return value ?? fallback;
}

export default async function SegmentationPage({
  searchParams,
}: SegmentationPageProps) {
  const params = searchParams ? await searchParams : {};
  const scaleUnit = getParam(params, "scaleUnit", "voxel") === "micron" ? "micron" : "voxel";
  const datasetContext: DatasetContext = {
    datasetId: getParam(params, "datasetId", "") || null,
    dataset: getParam(params, "dataset", "No dataset selected"),
    projectId: getParam(params, "projectId", "Pending"),
    dimensions: {
      x: getParam(params, "x", "unknown"),
      y: getParam(params, "y", "unknown"),
      z: getParam(params, "z", "unknown"),
    },
    voxelSizeMicron: getParam(params, "voxelSizeMicron", "unknown"),
    scaleUnit,
  };

  return <SegmentationClient datasetContext={datasetContext} />;
}
