import {
  WorkflowSidebar,
  buildWorkflowHref,
  type WorkflowStep,
} from "../components/WorkflowSidebar";
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
  const queryParams = new URLSearchParams(
    Object.entries(params).flatMap(([key, value]) => {
      if (Array.isArray(value)) {
        return value[0] === undefined ? [] : [[key, value[0]]];
      }

      return value === undefined ? [] : [[key, value]];
    }),
  );
  const workflowSteps: WorkflowStep[] = [
    {
      id: "project-dataset",
      href: buildWorkflowHref("/project-dataset"),
      state: "completed",
    },
    {
      id: "segmentation",
      href: buildWorkflowHref("/segmentation", queryParams),
      state: "completed",
    },
    {
      id: "structure-analysis",
      href: buildWorkflowHref("/structure-analysis", queryParams),
      state: "active",
    },
  ];

  return (
    <main className="workspace">
      <WorkflowSidebar steps={workflowSteps} />

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
