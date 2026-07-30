"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";

import {
  clampCutoff,
  formatMicrons,
  formatPercent,
  formatVolume,
  statusLabel,
  type MeasurementStatus,
} from "./measurementFormatting";
import {
  ThicknessMapCanvas,
  type ThicknessMapElement,
} from "./ThicknessMapCanvas";

type HistogramBin = {
  start_um: number;
  end_um: number;
  count: number;
};

type MeasurementPayload = {
  dataset_id: string;
  analysis_revision: string;
  generated_at: string;
  thickness: {
    target_um: number;
    critical_cutoff_um: number;
    user_cutoff_um: number;
    total_strut_count: number;
    eligible_strut_count: number;
    excluded_strut_count: number;
    mean_um: number;
    median_um: number;
    min_um: number;
    max_um: number;
    standard_deviation_um: number;
    below_target: { count: number; percent: number };
    below_critical: { count: number; percent: number };
    below_user_cutoff: { count: number; percent: number };
    histogram: {
      range_max_um: number;
      bins: HistogramBin[];
      overflow_count: number;
    };
    method: string;
    eligibility_rule: string;
  };
  relative_density: {
    segmented_volume_mm3: number;
    enclosing_volume_mm3: number;
    relative_density_percent: number;
    target_percent: number;
    difference_percentage_points: number;
    roi_definition: string;
    effective_voxel_size_mm: number;
  };
  comparison: {
    thickness_status: MeasurementStatus;
    relative_density_status: MeasurementStatus;
    overall_status: MeasurementStatus;
    policy: {
      version: string;
      provisional: boolean;
      approval_state: string;
    };
    reasons: string[];
    warning: string;
  };
  warnings: string[];
  provenance: {
    analysis_version: number;
    analysis_stride: number;
    voxel_size_mm: number;
    voxel_size_source: string;
    segmentation_threshold: number;
    threshold_source: string;
    coordinate_space: string;
  };
  thickness_map: {
    element_count: number;
    elements: ThicknessMapElement[];
  } | null;
};

type OutlierPayload = {
  cutoff_um: number;
  total_below_cutoff: number;
  truncated: boolean;
  struts: Array<{
    strut_id: number | string;
    measured_thickness_um: number;
    difference_from_cutoff_um: number;
    status: string;
  }>;
};

type CopilotToolResult = {
  tool_run_id: string;
  tool_name: string;
  specialist: "Measurement Orchestrator" | "Thickness Analysis Agent" | "Relative Density Agent";
  analysis_revision: string;
  summary: Record<string, unknown>;
  elements: Array<Record<string, unknown>>;
  evidence: Array<{
    artifact_id?: string;
    href?: string;
    kind?: string;
  }>;
  warnings: string[];
};

type CopilotResponse = {
  run_id: string;
  context_id: string;
  dataset_id: string;
  analysis_revision: string;
  mode: "openai-tool-calling" | "deterministic-local-orchestrator";
  model: string;
  answer: string;
  tool_results: CopilotToolResult[];
  viewer_actions: Array<{ type: string; strut_ids?: Array<number | string> }>;
  warnings: string[];
};

type ChatEntry = {
  id: string;
  role: "user" | "assistant";
  text: string;
  run?: CopilotResponse;
};

function analysisApiUrl() {
  return process.env.NEXT_PUBLIC_ANALYSIS_API_URL ?? "http://localhost:8000";
}

async function responseJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : null;
    throw new Error(detail ?? `Analysis API returned ${response.status}.`);
  }
  return payload as T;
}

function StatusBadge({ status }: { status: MeasurementStatus }) {
  return <span className={`measurement-status status-${status}`}>{statusLabel(status)}</span>;
}

function ThicknessHistogram({ data }: { data: MeasurementPayload["thickness"] }) {
  const width = 820;
  const height = 275;
  const margin = { left: 48, right: 20, top: 20, bottom: 42 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const maxCount = Math.max(1, ...data.histogram.bins.map((bin) => bin.count));
  const rangeMax = Math.max(1, data.histogram.range_max_um);
  const lineX = (value: number) => margin.left + (value / rangeMax) * innerWidth;
  const markers = [
    { value: data.critical_cutoff_um, label: "300 critical", className: "critical" },
    { value: data.target_um, label: "350 target", className: "target" },
    ...(data.user_cutoff_um !== data.target_um && data.user_cutoff_um !== data.critical_cutoff_um
      ? [{ value: data.user_cutoff_um, label: `${data.user_cutoff_um} cutoff`, className: "user" }]
      : []),
  ];

  return (
    <div className="measurement-chart-wrap">
      <svg
        aria-label="Strut thickness histogram in microns"
        className="measurement-histogram-chart"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        <line className="chart-axis" x1={margin.left} x2={margin.left} y1={margin.top} y2={margin.top + innerHeight} />
        <line className="chart-axis" x1={margin.left} x2={margin.left + innerWidth} y1={margin.top + innerHeight} y2={margin.top + innerHeight} />
        {data.histogram.bins.map((bin, index) => {
          const barWidth = innerWidth / data.histogram.bins.length;
          const barHeight = (bin.count / maxCount) * innerHeight;
          return (
            <rect
              className="histogram-bar"
              height={barHeight}
              key={`${bin.start_um}-${bin.end_um}`}
              width={Math.max(1, barWidth - 2)}
              x={margin.left + index * barWidth + 1}
              y={margin.top + innerHeight - barHeight}
            >
              <title>{`${bin.start_um.toFixed(1)}–${bin.end_um.toFixed(1)} µm: ${bin.count.toLocaleString()} struts`}</title>
            </rect>
          );
        })}
        {markers.map((marker) => {
          const x = lineX(marker.value);
          if (x < margin.left || x > margin.left + innerWidth) return null;
          return (
            <g className={`histogram-marker marker-${marker.className}`} key={marker.label}>
              <line x1={x} x2={x} y1={margin.top - 5} y2={margin.top + innerHeight} />
              <text x={x + 5} y={margin.top + 12}>{marker.label}</text>
            </g>
          );
        })}
        <text className="chart-label" x={margin.left} y={height - 10}>0 µm</text>
        <text className="chart-label" textAnchor="end" x={width - margin.right} y={height - 10}>{rangeMax.toFixed(0)} µm</text>
        <text className="chart-label" textAnchor="middle" transform={`rotate(-90 14 ${height / 2})`} x={14} y={height / 2}>Strut count</text>
      </svg>
      {data.histogram.overflow_count > 0 ? (
        <p className="histogram-overflow-note">
          {data.histogram.overflow_count.toLocaleString()} high-thickness values exceed the displayed range; they remain included in summary statistics.
        </p>
      ) : null}
    </div>
  );
}

function MetricCard({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <article className="measurement-metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {note ? <small>{note}</small> : null}
    </article>
  );
}

export function MeasurementClient({
  initialDatasetId,
  requestedThreshold,
}: {
  initialDatasetId: string;
  requestedThreshold: string;
}) {
  const [cutoffInput, setCutoffInput] = useState("350");
  const [activeCutoff, setActiveCutoff] = useState(350);
  const [payload, setPayload] = useState<MeasurementPayload | null>(null);
  const [outliers, setOutliers] = useState<OutlierPayload | null>(null);
  const [highlightedIds, setHighlightedIds] = useState<Array<number | string>>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [copilotInput, setCopilotInput] = useState("");
  const [copilotState, setCopilotState] = useState<"idle" | "running" | "error">("idle");
  const [copilotError, setCopilotError] = useState<string | null>(null);
  const [chatEntries, setChatEntries] = useState<ChatEntry[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const load = useCallback(async (cutoff: number) => {
    const query = new URLSearchParams({
      target_thickness_um: "350",
      critical_cutoff_um: "300",
      user_cutoff_um: String(cutoff),
      target_density_percent: "10",
      include_map: "true",
    });
    const base = `${analysisApiUrl()}/v1/datasets/${encodeURIComponent(initialDatasetId)}/measurements`;
    try {
      const [measurementResponse, outlierResponse] = await Promise.all([
        fetch(`${base}?${query}`, { cache: "no-store" }),
        fetch(`${base}/outliers?cutoff_um=${cutoff}&limit=10`, { cache: "no-store" }),
      ]);
      const [measurementPayload, outlierPayload] = await Promise.all([
        responseJson<MeasurementPayload>(measurementResponse),
        responseJson<OutlierPayload>(outlierResponse),
      ]);
      setPayload(measurementPayload);
      setOutliers(outlierPayload);
      setHighlightedIds([]);
      setState("ready");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Measurement analysis failed.";
      setError(
        message === "Failed to fetch"
          ? "Analysis API unavailable. Start it with npm run dev:api, then retry."
          : message,
      );
      setState("error");
    }
  }, [initialDatasetId]);

  useEffect(() => {
    // Fetching is the external synchronization performed by this effect; all
    // state updates inside load occur after the network promise settles.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load(activeCutoff);
  }, [activeCutoff, load]);

  const submitCutoff = (event: FormEvent) => {
    event.preventDefault();
    const nextCutoff = clampCutoff(Number(cutoffInput));
    setCutoffInput(String(nextCutoff));
    setState("loading");
    setError(null);
    setActiveCutoff(nextCutoff);
    if (nextCutoff === activeCutoff) void load(nextCutoff);
  };

  const askCopilot = async (question: string) => {
    if (!payload || !question.trim() || copilotState === "running") return;
    const cleanQuestion = question.trim();
    setCopilotState("running");
    setCopilotError(null);
    setChatEntries((entries) => [
      ...entries,
      { id: `user-${Date.now()}`, role: "user", text: cleanQuestion },
    ]);
    setCopilotInput("");
    try {
      const contextResponse = await fetch(`${analysisApiUrl()}/v1/measurement-copilot/contexts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: payload.dataset_id,
          target_thickness_um: payload.thickness.target_um,
          critical_cutoff_um: payload.thickness.critical_cutoff_um,
          user_cutoff_um: payload.thickness.user_cutoff_um,
          target_density_percent: payload.relative_density.target_percent,
          visible_statuses: [],
        }),
      });
      const context = await responseJson<{ context_id: string }>(contextResponse);
      let activeConversation = conversationId;
      if (!activeConversation) {
        activeConversation = `mconv_${crypto.randomUUID().replaceAll("-", "")}`;
        setConversationId(activeConversation);
      }
      const response = await fetch(
        `${analysisApiUrl()}/v1/measurement-copilot/conversations/${activeConversation}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ context_id: context.context_id, message: cleanQuestion }),
        },
      );
      const result = await responseJson<CopilotResponse>(response);
      for (const action of result.viewer_actions) {
        if (action.type === "highlight_struts" && action.strut_ids) {
          setHighlightedIds(action.strut_ids);
        }
      }
      setChatEntries((entries) => [
        ...entries,
        {
          id: result.run_id,
          role: "assistant",
          text: result.answer,
          run: result,
        },
      ]);
      setCopilotState("idle");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Measurement Copilot failed.";
      setCopilotError(
        message === "Failed to fetch"
          ? "Analysis API unavailable. Start it with npm run dev:api, then retry."
          : message,
      );
      setCopilotState("error");
    }
  };

  const submitCopilot = (event: FormEvent) => {
    event.preventDefault();
    void askCopilot(copilotInput);
  };

  const revision = payload?.analysis_revision.slice(0, 12) ?? "—";
  const thresholdMismatch = useMemo(() => {
    if (!payload || requestedThreshold === "Not provided") return false;
    const numeric = Number(requestedThreshold);
    return Number.isFinite(numeric) && numeric !== payload.provenance.segmentation_threshold;
  }, [payload, requestedThreshold]);

  return (
    <section className="content measurement-content">
      <div className="eyebrow">Quantitative evidence</div>
      <div className="measurement-title-row">
        <div>
          <h1>Measurement page</h1>
          <p className="lede">
            Determine whether the printed lattice matches its intended structure statistically, with deterministic thickness and density evidence.
          </p>
        </div>
        {payload ? <StatusBadge status={payload.comparison.overall_status} /> : null}
      </div>

      <section className="dataset-panel measurement-context" aria-label="Measurement dataset context">
        <dl className="project-meta measurement-meta">
          <div><dt>Dataset ID</dt><dd>{initialDatasetId}</dd></div>
          <div><dt>Analysis revision</dt><dd title={payload?.analysis_revision}>{revision}</dd></div>
          <div><dt>Analysis threshold</dt><dd>{payload?.provenance.segmentation_threshold ?? requestedThreshold}</dd></div>
          <div><dt>Policy</dt><dd>{payload?.comparison.policy.version ?? "demo-policy-v1"}</dd></div>
        </dl>
      </section>

      {thresholdMismatch ? (
        <div className="warning-banner" role="alert">
          The URL threshold differs from the persisted registered analysis. Results below cite threshold {payload?.provenance.segmentation_threshold}.
        </div>
      ) : null}

      {state === "loading" ? (
        <section className="dataset-panel measurement-loading" aria-live="polite">
          <span className="measurement-spinner" aria-hidden="true" />
          <div><strong>Computing registered measurements</strong><p>Loading the qualified analysis revision and registered design ROI.</p></div>
        </section>
      ) : null}

      {state === "error" ? (
        <section className="dataset-panel measurement-error" role="alert">
          <div><strong>Measurements unavailable</strong><p>{error}</p></div>
          <button onClick={() => { setState("loading"); setError(null); void load(activeCutoff); }} type="button">Retry</button>
        </section>
      ) : null}

      {payload ? (
        <div className="measurement-dashboard">
          <section className="dataset-panel measurement-section" aria-labelledby="thickness-heading">
            <div className="measurement-section-header">
              <div><p className="panel-kicker">Thickness Analysis Agent evidence</p><h2 id="thickness-heading">Strut thickness distribution</h2></div>
              <StatusBadge status={payload.comparison.thickness_status} />
            </div>
            <form className="measurement-cutoff-form" onSubmit={submitCutoff}>
              <label><span>User-defined cutoff</span><span className="input-with-unit"><input min="1" max="2000" onChange={(event) => setCutoffInput(event.target.value)} step="1" type="number" value={cutoffInput} /><span>µm</span></span></label>
              <button type="submit">Apply cutoff</button>
            </form>
            <ThicknessHistogram data={payload.thickness} />
            <div className="measurement-metric-grid">
              <MetricCard label="Mean" value={formatMicrons(payload.thickness.mean_um)} />
              <MetricCard label="Median" value={formatMicrons(payload.thickness.median_um)} />
              <MetricCard label="Minimum" value={formatMicrons(payload.thickness.min_um)} />
              <MetricCard label="Maximum" value={formatMicrons(payload.thickness.max_um)} />
              <MetricCard label="Below 350 µm" value={formatPercent(payload.thickness.below_target.percent)} note={`${payload.thickness.below_target.count.toLocaleString()} struts`} />
              <MetricCard label="Below 300 µm" value={formatPercent(payload.thickness.below_critical.percent)} note={`${payload.thickness.below_critical.count.toLocaleString()} struts`} />
              <MetricCard label={`Below ${payload.thickness.user_cutoff_um} µm`} value={formatPercent(payload.thickness.below_user_cutoff.percent)} note={`${payload.thickness.below_user_cutoff.count.toLocaleString()} struts`} />
              <MetricCard label="Eligible sample" value={payload.thickness.eligible_strut_count.toLocaleString()} note={`${payload.thickness.excluded_strut_count.toLocaleString()} excluded as unmeasured`} />
            </div>
          </section>

          <section className="dataset-panel measurement-section" aria-labelledby="map-heading">
            <div className="measurement-section-header">
              <div><p className="panel-kicker">Registered geometry</p><h2 id="map-heading">Thickness map</h2></div>
              <span className="state state-ready">{payload.thickness_map?.element_count.toLocaleString()} struts</span>
            </div>
            <p className="measurement-section-copy">Use the XY, XZ, and YZ projections to reduce 3D occlusion. Agent-selected outliers appear in white.</p>
            {payload.thickness_map ? (
              <ThicknessMapCanvas criticalCutoffUm={payload.thickness.critical_cutoff_um} elements={payload.thickness_map.elements} highlightedIds={highlightedIds} targetUm={payload.thickness.target_um} />
            ) : null}
          </section>

          <section className="measurement-density-layout">
            <article className="dataset-panel measurement-section" aria-labelledby="density-heading">
              <div className="measurement-section-header">
                <div><p className="panel-kicker">Relative Density Agent evidence</p><h2 id="density-heading">Relative density</h2></div>
                <StatusBadge status={payload.comparison.relative_density_status} />
              </div>
              <div className="density-gauge" style={{ "--density-position": `${Math.min(100, payload.relative_density.relative_density_percent / 20 * 100)}%`, "--target-position": `${payload.relative_density.target_percent / 20 * 100}%` } as CSSProperties}>
                <span className="density-fill" />
                <i className="density-target" title={`${payload.relative_density.target_percent}% target`} />
              </div>
              <div className="density-primary-value"><strong>{formatPercent(payload.relative_density.relative_density_percent)}</strong><span>target {formatPercent(payload.relative_density.target_percent)}</span></div>
              <dl className="density-volume-grid">
                <div><dt>Segmented strut volume</dt><dd>{formatVolume(payload.relative_density.segmented_volume_mm3)}</dd></div>
                <div><dt>Enclosing lattice volume</dt><dd>{formatVolume(payload.relative_density.enclosing_volume_mm3)}</dd></div>
                <div><dt>Difference from target</dt><dd>{payload.relative_density.difference_percentage_points > 0 ? "+" : ""}{payload.relative_density.difference_percentage_points.toFixed(3)} points</dd></div>
                <div><dt>ROI definition</dt><dd>{payload.relative_density.roi_definition.replaceAll("_", " ")}</dd></div>
              </dl>
            </article>

            <article className="dataset-panel measurement-section" aria-labelledby="outlier-heading">
              <div className="measurement-section-header">
                <div><p className="panel-kicker">Inspection queue</p><h2 id="outlier-heading">Lowest-thickness struts</h2></div>
                <button className="measurement-secondary-button" onClick={() => setHighlightedIds(outliers?.struts.map((item) => item.strut_id) ?? [])} type="button">Highlight 10</button>
              </div>
              <p className="measurement-section-copy">Ranked below the active {activeCutoff} µm cutoff. Values come from the registered EDT measurement.</p>
              <div className="measurement-table-wrap">
                <table className="measurement-table">
                  <thead><tr><th>Strut</th><th>Thickness</th><th>From cutoff</th><th>Status</th></tr></thead>
                  <tbody>
                    {outliers?.struts.map((item) => (
                      <tr key={item.strut_id}><td>#{item.strut_id}</td><td>{formatMicrons(item.measured_thickness_um)}</td><td>{formatMicrons(item.difference_from_cutoff_um)}</td><td>{item.status}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </section>

          <section className="dataset-panel measurement-section methodology-panel" aria-labelledby="method-heading">
            <div className="measurement-section-header"><div><p className="panel-kicker">Traceability</p><h2 id="method-heading">Method and limitations</h2></div><span className="state">Revision {revision}</span></div>
            <ul className="measurement-warning-list">{payload.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
            <dl className="measurement-provenance-grid">
              <div><dt>Thickness method</dt><dd>{payload.thickness.method.replaceAll("_", " ")}</dd></div>
              <div><dt>Eligibility</dt><dd>{payload.thickness.eligibility_rule}</dd></div>
              <div><dt>Voxel size</dt><dd>{payload.provenance.voxel_size_mm} mm</dd></div>
              <div><dt>Coordinate space</dt><dd>{payload.provenance.coordinate_space}</dd></div>
            </dl>
          </section>

          <section className="dataset-panel measurement-section measurement-copilot" aria-labelledby="copilot-heading">
            <div className="measurement-section-header">
              <div><p className="panel-kicker">Agentic analysis</p><h2 id="copilot-heading">Measurement Copilot</h2></div>
              <span className="state state-ready">Tool evidence required</span>
            </div>
            <p className="measurement-section-copy">
              Ask open-ended questions across thickness and density. The orchestrator delegates to deterministic specialist tools, cites their runs, and can highlight returned struts.
            </p>
            <div className="copilot-suggestions" aria-label="Suggested measurement questions">
              {[
                "Does this print match the intended structure statistically? Highlight the ten worst struts.",
                `What changes if I use the ${activeCutoff} micron cutoff?`,
                "Explain the relative density result and its ROI caveats.",
                "Generate a measurement report.",
              ].map((suggestion) => (
                <button disabled={copilotState === "running"} key={suggestion} onClick={() => void askCopilot(suggestion)} type="button">{suggestion}</button>
              ))}
            </div>
            <div className="copilot-thread" aria-live="polite">
              {chatEntries.length === 0 ? (
                <div className="copilot-empty-state"><strong>No agent run yet</strong><span>Try the design-match question to invoke both specialist workflows.</span></div>
              ) : chatEntries.map((entry) => (
                <article className={`copilot-message copilot-message-${entry.role}`} key={entry.id}>
                  <span className="copilot-role">{entry.role === "user" ? "You" : "Measurement Copilot"}</span>
                  <p>{entry.text}</p>
                  {entry.run ? (
                    <div className="copilot-run-details">
                      <div className="copilot-run-meta">
                        <span>{entry.run.mode === "openai-tool-calling" ? `OpenAI · ${entry.run.model}` : "Deterministic local orchestrator"}</span>
                        <span>Run {entry.run.run_id}</span>
                        <span>Revision {entry.run.analysis_revision.slice(0, 12)}</span>
                      </div>
                      <details>
                        <summary>{entry.run.tool_results.length} deterministic tool call{entry.run.tool_results.length === 1 ? "" : "s"}</summary>
                        <ol className="copilot-tool-trace">
                          {entry.run.tool_results.map((tool) => (
                            <li key={tool.tool_run_id}>
                              <span><strong>{tool.specialist}</strong><code>{tool.tool_name}</code></span>
                              <small>{tool.tool_run_id}</small>
                            </li>
                          ))}
                        </ol>
                      </details>
                      {entry.run.tool_results.flatMap((tool) => tool.evidence).filter((evidence) => evidence.kind === "measurement_report" && evidence.href).map((evidence) => (
                        <a className="copilot-artifact-link" href={`${analysisApiUrl()}${evidence.href}`} key={evidence.artifact_id}>Download Markdown measurement report</a>
                      ))}
                      {entry.run.warnings.map((warning) => <p className="copilot-warning" key={warning}>{warning}</p>)}
                    </div>
                  ) : null}
                </article>
              ))}
              {copilotState === "running" ? (
                <div className="copilot-running"><span className="measurement-spinner" aria-hidden="true" /><span>Orchestrator is selecting deterministic tools…</span></div>
              ) : null}
            </div>
            {copilotError ? <p className="inline-error" role="alert">{copilotError}</p> : null}
            <form className="copilot-composer" onSubmit={submitCopilot}>
              <label htmlFor="measurement-copilot-input">Ask about this measurement revision</label>
              <div>
                <textarea id="measurement-copilot-input" onChange={(event) => setCopilotInput(event.target.value)} placeholder="Does the print match the intended structure statistically?" rows={3} value={copilotInput} />
                <button disabled={copilotState === "running" || !copilotInput.trim()} type="submit">Analyze</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </section>
  );
}
