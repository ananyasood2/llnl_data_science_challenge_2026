type MeasurementsPageProps = {
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

const plannedMeasurements = [
  {
    title: "Strut thickness",
    description:
      "Distribution, mean, median, minimum, maximum, and percentages below the target and user-defined cutoffs.",
  },
  {
    title: "Thickness map",
    description:
      "Color-coded struts for locating thin, nominal, and thick regions in the registered lattice.",
  },
  {
    title: "Relative density",
    description:
      "Segmented material volume compared with the enclosing registered lattice volume and the 10% design target.",
  },
  {
    title: "Measurement agents",
    description:
      "Evidence-backed thickness and density interpretation using deterministic analysis results.",
  },
];

export default async function MeasurementsPage({
  searchParams,
}: MeasurementsPageProps) {
  const params = searchParams ? await searchParams : {};
  const datasetId = getParam(params, "datasetId", "missing_struts");
  const threshold = getParam(params, "threshold", "Not provided");

  return (
    <section className="content measurement-content">
      <div className="eyebrow">Quantitative evidence</div>
      <h1>Measurement page</h1>
      <p className="lede">
        Evaluate whether the printed lattice matches its intended structure using
        strut-thickness and relative-density measurements.
      </p>

      <section
        className="dataset-panel measurement-context"
        aria-label="Measurement dataset context"
      >
        <dl className="project-meta">
          <div>
            <dt>Dataset ID</dt>
            <dd>{datasetId}</dd>
          </div>
          <div>
            <dt>Segmentation threshold</dt>
            <dd>{threshold}</dd>
          </div>
        </dl>
      </section>

      <div className="measurement-grid" aria-label="Planned measurement features">
        {plannedMeasurements.map((measurement) => (
          <article className="foundation-card measurement-card" key={measurement.title}>
            <div className="card-heading">
              <span>{measurement.title}</span>
              <span className="state">Planned</span>
            </div>
            <p>{measurement.description}</p>
          </article>
        ))}
      </div>

      <aside className="notice measurement-notice" role="status">
        This page is ready for measurement data integration. No scientific values
        are estimated or fabricated in this scaffold.
      </aside>
    </section>
  );
}
