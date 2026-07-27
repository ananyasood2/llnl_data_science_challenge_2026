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
  const dataset = getParam(params, "dataset", "No dataset selected");
  const projectId = getParam(params, "projectId", "Pending");
  const x = getParam(params, "x", "unknown");
  const y = getParam(params, "y", "unknown");
  const z = getParam(params, "z", "unknown");
  const voxelSizeMicron = getParam(params, "voxelSizeMicron", "unknown");

  return (
    <main className="workspace">
      <aside className="rail" aria-label="Pipeline context">
        <div className="mark" aria-hidden="true">
          ◈
        </div>
        <div>
          <p className="rail-kicker">Step 2</p>
          <p className="rail-title">Segmentation</p>
        </div>
        <div className="rail-rule" />
        <span className="status-pill">
          <span aria-hidden="true">●</span> Route stub
        </span>
        <p className="rail-copy">
          This page will host segmentation controls after the analysis-job contract is
          defined.
        </p>
      </aside>

      <section className="content dataset-content">
        <div className="eyebrow">Segmentation</div>
        <h1>Segmentation setup</h1>
        <p className="lede">
          Dataset context was received from project intake. Backend job creation is
          intentionally deferred until the analysis-job API contract exists.
        </p>

        <section className="dataset-panel segmentation-summary" aria-labelledby="segmentation-summary-heading">
          <div className="section-heading">
            <p className="panel-kicker">Dataset context</p>
            <h2 id="segmentation-summary-heading">Segmentation — dataset: {dataset}</h2>
          </div>
          <dl className="project-meta">
            <div>
              <dt>Project ID</dt>
              <dd>{projectId}</dd>
            </div>
            <div>
              <dt>Dimensions</dt>
              <dd>
                {x}, {y}, {z}
              </dd>
            </div>
            <div>
              <dt>Voxel size</dt>
              <dd>{voxelSizeMicron} micron</dd>
            </div>
          </dl>
        </section>
      </section>
    </main>
  );
}
