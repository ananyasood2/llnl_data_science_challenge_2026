import { getStructureViewerUrl } from "./viewerConfig";
import { StructureViewerFrame } from "./StructureViewerFrame";

type StructureAnalysisPageProps = {
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

export default async function StructureAnalysisPage({
  searchParams,
}: StructureAnalysisPageProps) {
  const params = searchParams ? await searchParams : {};
  const viewerUrl = getStructureViewerUrl(
    process.env.NEXT_PUBLIC_STRUCTURE_VIEWER_URL,
  );
  const datasetId = getParam(params, "datasetId", "");
  const threshold = getParam(params, "threshold", "Not provided");
  const usingDefaultDataset = datasetId.length === 0;

  return (
    <>
      <section className="content structure-content">
        <div className="eyebrow">Validation</div>
        <h1>3D structure analysis</h1>
        {usingDefaultDataset ? (
          <p className="default-dataset-indicator" role="status">
            Default dataset: missing_struts
          </p>
        ) : null}

        <section className="dataset-panel structure-context" aria-label="Structure analysis context">
          <dl className="project-meta">
            <div>
              <dt>Dataset ID</dt>
              <dd>{usingDefaultDataset ? "missing_struts" : datasetId}</dd>
            </div>
            <div>
              <dt>Threshold</dt>
              <dd>{threshold}</dd>
            </div>
            <div>
              <dt>Viewer URL</dt>
              <dd>{viewerUrl}</dd>
            </div>
          </dl>
        </section>

        <StructureViewerFrame viewerUrl={viewerUrl} />
      </section>
    </>
  );
}
