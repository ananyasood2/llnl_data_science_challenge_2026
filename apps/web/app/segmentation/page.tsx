import {
  DatasetContext,
  SegmentationClient,
  type SegmentationQueryParams,
} from "./SegmentationClient";
import Link from "next/link";

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

function getQueryParams(params: Record<string, string | string[] | undefined>) {
  return Object.fromEntries(
    Object.entries(params).flatMap(([key, value]) => {
      if (Array.isArray(value)) {
        return value[0] === undefined ? [] : [[key, value[0]]];
      }

      return value === undefined ? [] : [[key, value]];
    }),
  ) satisfies SegmentationQueryParams;
}

export default async function SegmentationPage({
  searchParams,
}: SegmentationPageProps) {
  const params = searchParams ? await searchParams : {};
  const scaleUnit = getParam(params, "scaleUnit", "voxel") === "micron" ? "micron" : "voxel";
  const datasetContext: DatasetContext = {
    datasetId: getParam(params, "datasetId", "") || null,
    jobId: getParam(params, "jobId", "") || null,
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

  if (!datasetContext.datasetId) {
    return (
      <section className="content dataset-content">
        <div className="eyebrow">Segmentation</div>
        <h1>CT preparation</h1>
        <p className="lede">
          Choose a persisted dataset before opening slice preparation. The workflow
          navigation remains available, but CT preparation needs dataset context to
          retrieve slices and save masks.
        </p>

        <section className="dataset-panel empty-state" aria-labelledby="ct-empty-heading">
          <div className="section-heading">
            <p className="panel-kicker">Dataset context required</p>
            <h2 id="ct-empty-heading">No dataset selected</h2>
          </div>
          <p>
            Start from Project / Dataset to upload or validate a CT volume, then continue
            here with the generated dataset context.
          </p>
          <Link className="primary-link" href="/project-dataset">
            Choose dataset
          </Link>
        </section>
      </section>
    );
  }

  return (
    <SegmentationClient
      datasetContext={datasetContext}
      queryParams={getQueryParams(params)}
    />
  );
}
