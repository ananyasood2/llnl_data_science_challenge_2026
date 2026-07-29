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
  const datasetId = getParam(params, "datasetId", "No dataset selected");
  const threshold = getParam(params, "threshold", "Not provided");

  return (
    <main className="workspace">
      <aside className="rail" aria-label="Pipeline context">
        <div className="mark" aria-hidden="true">
          ◈
        </div>
        <div>
          <p className="rail-kicker">Step 3</p>
          <p className="rail-title">3D Structure Analysis</p>
        </div>
        <div className="rail-rule" />
        <span className="status-pill">
          <span aria-hidden="true">●</span> Dash viewer
        </span>
        <p className="rail-copy">
          Validate the prepared CT segmentation using the existing 3D Dash dashboard.
        </p>
      </aside>

      <section className="content structure-content">
        <div className="eyebrow">Validation</div>
        <h1>3D structure analysis</h1>

        <section className="dataset-panel structure-context" aria-label="Structure analysis context">
          <dl className="project-meta">
            <div>
              <dt>Dataset ID</dt>
              <dd>{datasetId}</dd>
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
    </main>
  );
}
