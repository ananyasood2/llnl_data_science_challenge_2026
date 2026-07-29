"use client";
/* eslint-disable @typescript-eslint/no-unused-vars */

import { FormEvent, PointerEvent, WheelEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import ThreeLatticeViewer, { Visibility } from "./components/ThreeLatticeViewer";
import Part1IsoSurfaceViewer from "./components/Part1IsoSurfaceViewer";

type Mode = "tiff" | "json" | "overlay";
type Status = "missing" | "broken" | "disconnected" | "thin" | "clear";

const files = [
  { kind: "TIFF volume", name: "210127_Brian_Tran...Slices.tif", meta: "761 × 815 × 837 voxels", selected: true },
  { kind: "Registered graph", name: "210127_Brian_Tran...Slices.json", meta: "18,468 struts · 4,913 nodes" },
  { kind: "Screening result", name: "per_strut_verdicts.json", meta: "18,468 image-derived strut verdicts" },
  { kind: "Nominal geometry", name: "octet_truss_9x9x9.json", meta: "Reference lattice" },
];

const baseSamples: Array<{ id: number; material: number; gap: number; status: Status }> = [
  { id: 5, material: .06, gap: 29, status: "missing" }, { id: 10, material: 0, gap: 31, status: "missing" },
  { id: 4, material: .16, gap: 14, status: "disconnected" }, { id: 47, material: .27, gap: 13, status: "disconnected" },
  { id: 87, material: .48, gap: 10, status: "broken" }, { id: 112, material: .53, gap: 8, status: "broken" },
  { id: 239, material: .63, gap: 4, status: "thin" }, { id: 301, material: .69, gap: 2, status: "thin" },
  { id: 1, material: 1, gap: 0, status: "clear" }, { id: 6, material: .84, gap: 3, status: "clear" },
];

const statusInfo: Record<Status, { label: string; color: string; baseline: number }> = {
  missing: { label: "Missing", color: "#e65c43", baseline: 2110 }, broken: { label: "Broken", color: "#bf7947", baseline: 842 },
  disconnected: { label: "Disconnected", color: "#d49536", baseline: 6025 }, thin: { label: "Thin", color: "#9074c6", baseline: 1491 }, clear: { label: "Clear", color: "#26836f", baseline: 8000 },
};

function classify(sample: typeof baseSamples[number], materialCutoff: number, gapCutoff: number): Status {
  if (sample.material <= materialCutoff * .45) return "missing";
  if (sample.gap >= gapCutoff + 4) return "disconnected";
  if (sample.gap >= gapCutoff) return "broken";
  if (sample.material < materialCutoff + .22) return "thin";
  return "clear";
}

const issues = [
  { id: "S-005", status: "missing" as Status, x: 172, y: 188 },
  { id: "S-047", status: "disconnected" as Status, x: 219, y: 213 },
  { id: "S-087", status: "broken" as Status, x: 266, y: 238 },
  { id: "S-239", status: "thin" as Status, x: 313, y: 263 },
];

function Graph({ mode, rotation, zoom, active, selectedIssue, onSelectIssue }: { mode: Mode; rotation: number; zoom: number; active: Status | "all"; selectedIssue: string | null; onSelectIssue: (id: string) => void }) {
  const paths = useMemo(() => Array.from({ length: 36 }, (_, i) => {
    const row = Math.floor(i / 6), col = i % 6, x = 74 + col * 55 + row * 16 + rotation * (row - 2) * .18, y = 102 + row * 50 - col * 10;
    const status: Status = i === 15 ? "missing" : i === 20 ? "disconnected" : i === 27 ? "broken" : i === 8 ? "thin" : "clear";
    return { d: `M${x},${y} L${x + 70},${y - 20} M${x},${y} L${x + 16},${y + 50} M${x + 70},${y - 20} L${x + 16},${y + 50}`, status };
  }), [rotation]);
  return <svg className="graph" viewBox="0 0 480 410" role="img" aria-label={`${mode} 3D comparison view`}>
    <g transform={`translate(240 205) scale(${zoom}) translate(-240 -205)`}>
      <g className="graph-axis"><path d="M34 355 L86 335 M34 355 L34 304 M34 355 L64 370"/><text x="91" y="338">X</text><text x="29" y="296">Z</text><text x="68" y="377">Y</text></g>
      {mode === "tiff" && <g className="voxel-cloud">{Array.from({ length: 60 }, (_, i) => <circle key={i} cx={70 + (i * 41) % 340} cy={90 + (i * 69) % 230} r={12 + (i % 4) * 3} />)}</g>}
      {mode !== "tiff" && <g className="graph-lines">{paths.map((path, i) => <path key={i} d={path.d} className={(active === "all" || active === path.status || path.status === "clear") ? path.status : "muted"} />)}</g>}
      {mode === "overlay" && <g className="issue-points">{issues.map(issue => (active === "all" || active === issue.status) && <g key={issue.id} className="issue-marker" onClick={() => onSelectIssue(issue.id)}><circle cx={issue.x} cy={issue.y} r="10" fill={statusInfo[issue.status].color} /><circle cx={issue.x} cy={issue.y} r="4" /><title>{`${issue.id}: ${statusInfo[issue.status].label}`}</title>{selectedIssue === issue.id && <g className="issue-label" style={{ color: statusInfo[issue.status].color }}><path d={`M${issue.x + 7} ${issue.y - 7} L${issue.x + 21} ${issue.y - 25}`} /><rect x={issue.x + 20} y={issue.y - 39} width="108" height="28" rx="3" /><text x={issue.x + 27} y={issue.y - 27}>{issue.id}</text><text x={issue.x + 27} y={issue.y - 17}>{statusInfo[issue.status].label}</text></g>}</g>)}</g>}
    </g>
  </svg>;
}

export default function HomePage() {
  const [mode, setMode] = useState<Mode>("overlay");
  const [active, setActive] = useState<Status | "all">("all");
  const [visibleGroups, setVisibleGroups] = useState<Visibility>({ clear: true, missing: true, disconnected: true, thin: true, broken: true });
  const [rotation, setRotation] = useState(24);
  const [zoom, setZoom] = useState(1);
  const [selectedIssue, setSelectedIssue] = useState<string | null>("S-005");
  const dragStart = useRef<{ x: number; rotation: number } | null>(null);
  const [materialCutoff, setMaterialCutoff] = useState(.38);
  const [gapCutoff, setGapCutoff] = useState(9);
  const [slice, setSlice] = useState(380);
  const [liveCounts, setLiveCounts] = useState<Record<Status, number> | null>(null);
  const [artifactCounts, setArtifactCounts] = useState<{ missing?: number; disconnected?: number; missing_candidate?: number; disconnected_candidate?: number } | null>(null);
  const [chatQuestion, setChatQuestion] = useState("");
  const [chatAnswer, setChatAnswer] = useState("Ask about registration, candidate counts, repair, or the saved file inventory.");
  const [chatSources, setChatSources] = useState<string[]>([]);
  const [researchMethod, setResearchMethod] = useState("Registered graph + CT-support screening");
  const [agentTask, setAgentTask] = useState("");
  const [agentStatus, setAgentStatus] = useState("Ready to inspect the loaded dataset and saved evidence.");
  const [agentOutput, setAgentOutput] = useState<{ answer: string; sources: string[] } | null>(null);
  const [part1Slice, setPart1Slice] = useState(128);
  const [part1Summary, setPart1Summary] = useState<{ score: number; comment: string; foreground_voxels: number; skeleton_voxels: number; threshold: number } | null>(null);
  const [selectedStrut, setSelectedStrut] = useState<{ id: number; classification: string; support: number; gap: number; a: number[]; b: number[] } | null>(null);
  const [uploads, setUploads] = useState<{ tiff?: string; json?: string; stl?: string }>({});
  const [uploadFiles, setUploadFiles] = useState<{ tiff?: File; json?: File; stl?: File }>({});
  const [uploadRunStatus, setUploadRunStatus] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | undefined>();
  const [metricsTrue, setMetricsTrue] = useState("");
  const [metricsPred, setMetricsPred] = useState("");
  const [metricsPredCount, setMetricsPredCount] = useState<number | null>(null);
  const [secondOpinion, setSecondOpinion] = useState<string | null>(null);
  const [metricsAverage, setMetricsAverage] = useState<"binary" | "macro" | "weighted">("binary");
  const [metricsPositive, setMetricsPositive] = useState("missing");
  const [metricsResult, setMetricsResult] = useState<{ accuracy: number; precision: number; recall: number; f1: number } | null>(null);
  const [metricsError, setMetricsError] = useState("");
  const classified = useMemo(() => baseSamples.map(s => classify(s, materialCutoff, gapCutoff)), [materialCutoff, gapCutoff]);
  const stats = useMemo(() => (Object.keys(statusInfo) as Status[]).map(status => {
    const portion = classified.filter(value => value === status).length / classified.length;
    return { status, count: Math.round(statusInfo[status].baseline * (status === "clear" ? Math.max(.4, portion * 1.8) : Math.max(.2, portion * 2))) };
  }), [classified]);
  const beginRotate = (event: PointerEvent<HTMLDivElement>) => { dragStart.current = { x: event.clientX, rotation }; event.currentTarget.setPointerCapture(event.pointerId); };
  const rotateView = (event: PointerEvent<HTMLDivElement>) => { if (dragStart.current) setRotation(Math.max(-45, Math.min(45, dragStart.current.rotation + (event.clientX - dragStart.current.x) * .3))); };
  const endRotate = () => { dragStart.current = null; };
  const zoomView = (event: WheelEvent<HTMLDivElement>) => { event.preventDefault(); setZoom(value => Math.max(.72, Math.min(1.55, value - event.deltaY * .001))); };
  useEffect(() => { fetch("/api/pipeline").then(response => response.json()).then(data => setArtifactCounts(data.inspection?.counts ?? null)).catch(() => undefined); }, []);
  useEffect(() => { const select = (event: Event) => setSelectedStrut((event as CustomEvent<typeof selectedStrut>).detail); window.addEventListener("lattice-strut-selected", select); return () => window.removeEventListener("lattice-strut-selected", select); }, []);
  useEffect(() => { fetch(`${process.env.NEXT_PUBLIC_ANALYSIS_API_URL ?? "http://127.0.0.1:8000"}/api/v1/part1/summary`).then(response => response.ok ? response.json() : null).then(data => setPart1Summary(data)).catch(() => undefined); }, []);
  useEffect(() => { let cancelled = false; const url = activeRunId ? `/api/viewer?run=${encodeURIComponent(activeRunId)}` : "/api/viewer"; fetch(url).then(response => response.json()).then(data => { if (cancelled) return; const counts: Record<Status, number> = { missing: 0, disconnected: 0, broken: 0, thin: 0, clear: 0 }; const predictions: string[] = []; const secondOpinions: string[] = []; data.struts.forEach((strut: { classification: Status; second_opinion: Status | null }) => { counts[strut.classification] += 1; predictions.push(strut.classification); if (strut.second_opinion) secondOpinions.push(strut.second_opinion); }); setLiveCounts(counts); setMetricsPred(predictions.join(",")); setMetricsPredCount(predictions.length); setSecondOpinion(data.secondOpinionAvailable ? secondOpinions.join(",") : null); }).catch(() => undefined); return () => { cancelled = true; }; }, [activeRunId]);
  const askCopilot = async (event: FormEvent) => { event.preventDefault(); if (!chatQuestion.trim()) return; const response = await fetch("/api/copilot", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: chatQuestion, context: { slice, visibleGroups, run: activeRunId ?? "saved registered run" } }) }); const data = await response.json(); setChatAnswer(data.answer); setChatSources(data.sources ?? []); };
  const runAgentTask = async () => { const task = agentTask.trim(); if (!task) { setAgentStatus("Describe an exploration task first, for example: compare candidate density near the current slice."); return; } setChatQuestion(task); setAgentOutput(null); setAgentStatus("Analyzing the current viewport and saved evidence..."); try { const response = await fetch("/api/copilot", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: task, context: { slice, visibleGroups, run: activeRunId ?? "saved registered run" } }) }); const data = await response.json(); if (!response.ok) throw new Error(data.detail ?? "Analysis request failed."); setAgentOutput({ answer: data.answer, sources: data.sources ?? [] }); setChatAnswer(data.answer); setChatSources(data.sources ?? []); setAgentStatus("Analysis complete."); } catch (error) { setAgentStatus(error instanceof Error ? error.message : "Analysis request failed."); } };
  const runUploadedInspection = async () => { if (!uploadFiles.tiff || !uploadFiles.json) { setUploadRunStatus("Select both a TIFF and its registered JSON before running."); return; } setUploadRunStatus("Uploading files and running registered inspection..."); const form = new FormData(); form.append("tiff", uploadFiles.tiff); form.append("json", uploadFiles.json); if (uploadFiles.stl) form.append("stl", uploadFiles.stl); try { const response = await fetch("/api/uploads/run", { method: "POST", body: form }); const data = await response.json(); if (response.ok) { setActiveRunId(data.runId); setUploadRunStatus(`Completed ${data.runId}. Loading its 3D views now.`); } else setUploadRunStatus(data.detail ?? "Upload run failed."); } catch { setUploadRunStatus("Upload run failed. Check the local server output."); } };
  const totalFlagged = (liveCounts?.missing ?? artifactCounts?.missing ?? 0) + (liveCounts?.disconnected ?? artifactCounts?.disconnected ?? 0);
  const runMetrics = useCallback(async () => {
    const yTrue = metricsTrue.split(",").map(value => value.trim()).filter(Boolean);
    const yPred = metricsPred.split(",").map(value => value.trim()).filter(Boolean);
    if (yTrue.length === 0) { setMetricsResult(null); setMetricsError(""); return; }
    if (yTrue.length !== yPred.length) { setMetricsResult(null); setMetricsError(`Ground truth has ${yTrue.length} label(s) but the live run has ${yPred.length} prediction(s) — lengths must match.`); return; }
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_ANALYSIS_API_URL}/api/v1/metrics/classification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ y_true: yTrue, y_pred: yPred, average: metricsAverage, positive_label: metricsAverage === "binary" ? metricsPositive : undefined }),
      });
      const data = await response.json();
      if (!response.ok) { setMetricsError(data.detail ?? "Metrics request failed."); return; }
      setMetricsError(""); setMetricsResult(data);
    } catch { setMetricsError("Could not reach the analysis API. Is it running on :8000?"); }
  }, [metricsTrue, metricsPred, metricsAverage, metricsPositive]);
  useEffect(() => { const timer = setTimeout(() => { runMetrics(); }, 400); return () => clearTimeout(timer); }, [runMetrics]);
  const computeMetrics = (event: FormEvent) => { event.preventDefault(); runMetrics(); };

  return <main className="inspect-app">
    <header><div className="wordmark"><span>◈</span> Lattice Inspect <b>COMPARE</b></div><div className="run"><i/> Registered CT + graph <small>210127_Brian_Tran · Part 2</small></div></header>
    <div className="layout">
      <aside className="source-panel"><div className="eyebrow">Comparison files</div><h2>Loaded sources</h2>{files.map(file => <button className={`file-row ${file.selected ? "loaded" : ""}`} key={file.name}><span className="file-type">{file.kind === "TIFF volume" ? "TIFF" : file.kind === "Registered graph" ? "JSON" : "CSV"}</span><span><strong>{file.name}</strong><small>{file.meta}</small></span>{file.selected && <em>Ready</em>}</button>)}<div className="upload-area"><div className="eyebrow">Add input files</div><label>TIFF volume<input type="file" accept=".tif,.tiff" onChange={event => { const file = event.target.files?.[0]; setUploads(current => ({ ...current, tiff: file?.name })); setUploadFiles(current => ({ ...current, tiff: file })); }}/><small>{uploads.tiff ?? "No file selected"}</small></label><label>Registered JSON<input type="file" accept=".json" onChange={event => { const file = event.target.files?.[0]; setUploads(current => ({ ...current, json: file?.name })); setUploadFiles(current => ({ ...current, json: file })); }}/><small>{uploads.json ?? "No file selected"}</small></label><label>STL design<input type="file" accept=".stl" onChange={event => { const file = event.target.files?.[0]; setUploads(current => ({ ...current, stl: file?.name })); setUploadFiles(current => ({ ...current, stl: file })); }}/><small>{uploads.stl ? `${uploads.stl} - registration required` : "No file selected"}</small></label><button className="run-upload" onClick={runUploadedInspection}>Run inspection</button>{uploadRunStatus && <small className="upload-status">{uploadRunStatus}</small>}</div><div className="source-note">CT and design comparisons run only after a registered TIFF/JSON pair is confirmed; STL files require explicit registration.</div></aside>
      <section className="workspace">
        <div className="workspace-head"><div><div className="eyebrow">Interactive inspection</div><h1>Registered lattice geometry</h1></div></div>
        <article className="combined-view"><div className="view-label"><span className="dot coral"/> Lit 3D geometry <small>Registered JSON + screening candidates</small></div><ThreeLatticeViewer visible={visibleGroups} slice={slice} runId={activeRunId}/><div className="combined-footer"><span>Drag to orbit · scroll to zoom · shaded tubes use physical voxel scale</span><span>Only strong Missing and Disconnected detector candidates are highlighted.</span></div></article><section className="defect-overview"><div><div className="eyebrow">Whole-run error overview</div><h2>Defect classes</h2><p className="flag-total">Total flagged: <strong>{totalFlagged.toLocaleString()}</strong> ({((totalFlagged / 18468) * 100).toFixed(1)}%)</p></div><div className="defect-cards">{(["missing", "disconnected"] as Status[]).map(kind => { const count = liveCounts?.[kind] ?? (kind === "missing" ? artifactCounts?.missing_candidate ?? 0 : artifactCounts?.disconnected_candidate ?? 0); return <button className={`defect-card ${visibleGroups[kind] ? "active" : ""}`} key={kind} onClick={() => setVisibleGroups(groups => ({ ...groups, [kind]: !groups[kind] }))}><span style={{ background: statusInfo[kind].color }}/><strong>{statusInfo[kind].label}</strong><b>{count.toLocaleString()}</b><small>{((count / 18468) * 100).toFixed(1)}% of struts</small></button>; })}</div></section>
        <section className="agent-workbench" aria-label="Autonomous data explorer and visual reasoner"><div className="agent-heading"><div><div className="eyebrow">Agentic analysis workspace</div><h2>Explore, reason, and document</h2></div><span className="agent-live"><i/> Evidence-linked</span></div><div className="agent-cards"><article><span className="agent-number">01</span><h3>Autonomous Data Explorer</h3><p>Inventories TIFF, JSON, STL, verdict, and report artifacts; then selects registered screening, segmentation, graph comparison, or repair methods.</p><label>Selected method<select value={researchMethod} onChange={event => setResearchMethod(event.target.value)}><option>Registered graph + CT-support screening</option><option>Threshold optimization + segmentation review</option><option>Graph connectivity + repair comparison</option></select></label><small>Method notes and source artifacts remain traceable in the run.</small></article><article><span className="agent-number">02</span><h3>Visual Reasoner</h3><p>Uses the rendered lattice, active classes, and CT slice as evidence—not a claimed ground-truth verdict.</p><div className="viewport-readout"><span>Current context</span><strong>Slice {slice} · {Object.values(visibleGroups).filter(Boolean).length}/5 layers visible</strong></div><label className="reasoner-slice">CT slice <output>{slice} / 760</output><input type="range" min="0" max="760" value={slice} onChange={event => setSlice(Number(event.target.value))}/></label><small>Hover a strut to inspect its nodes, support, gap, thickness, and confidence.</small></article><article><span className="agent-number">03</span><h3>Interactive Co-Pilot</h3><p>Turn the current 3D view into a reproducible question for the evidence-backed co-pilot.</p><textarea value={agentTask} onChange={event => setAgentTask(event.target.value)} placeholder="e.g., Compare missing candidates near this slice and recommend a verification step." rows={3}/><button onClick={runAgentTask}>Analyze current viewport</button><small>{agentStatus}</small>{agentOutput && <div className="agent-output"><strong>Analysis output</strong><p>{agentOutput.answer}</p>{agentOutput.sources.length > 0 && <small>Sources: {agentOutput.sources.join(", ")}</small>}</div>}</article></div></section>
        <section className="part1-evidence"><div className="part1-head"><div><div className="eyebrow">Part 1 model evidence</div><h2>CT segmentation, flags, and 3D structure</h2></div>{part1Summary && <div className="part1-score"><span>Segmentation score</span><strong>{part1Summary.score} / 4</strong><small>Visual rubric result</small></div>}</div>{part1Summary && <p className="part1-comment">{part1Summary.comment}</p>}<div className="part1-grid"><article className="slice-evidence"><div className="view-label"><span className="dot teal"/> Live CT + segmentation + skeleton <small>z = {part1Slice}</small></div><img src={`${process.env.NEXT_PUBLIC_ANALYSIS_API_URL ?? "http://127.0.0.1:8000"}/api/v1/part1/slice.png?z=${part1Slice}`} alt={`Part 1 CT, segmentation, and skeleton at slice ${part1Slice}`}/><div className="slice-legend"><span><i className="raw"/> CT</span><span><i className="mask"/> Segmentation</span><span><i className="skeleton"/> Skeleton</span></div><label className="part1-slider">Part 1 CT slice <output>{part1Slice} / 255</output><input type="range" min="0" max="255" value={part1Slice} onChange={event => setPart1Slice(Number(event.target.value))}/></label></article><article className="iso-evidence"><div className="view-label"><span className="dot blue"/> 3D isosurface with skeleton <small>Saved NDE views</small></div><div className="iso-gallery"><figure><img src="http://127.0.0.1:8000/assets/part1/view_a.png" alt="Part 1 3D isosurface and skeleton, view A"/><figcaption>View A · elevation 30°</figcaption></figure><figure><img src="http://127.0.0.1:8000/assets/part1/view_b.png" alt="Part 1 3D isosurface and skeleton, view B"/><figcaption>View B · elevation 60°</figcaption></figure></div><p>{part1Summary ? `${part1Summary.foreground_voxels.toLocaleString()} segmented voxels · ${part1Summary.skeleton_voxels.toLocaleString()} skeleton voxels · Otsu threshold ${part1Summary.threshold}.` : "Loading saved Part 1 structural metrics..."}</p></article></div></section>
        <section className="live-isosurface"><div className="view-label"><span className="dot blue"/> Live 3D isosurface with skeleton <small>Mask and skeleton reloaded from Part 1 analysis artifacts</small><em>Drag to orbit · scroll to zoom</em></div><Part1IsoSurfaceViewer refreshKey={activeRunId ?? "part1-saved-run"}/></section>
        {selectedStrut && <section className="point-verification"><div><div className="eyebrow">Selected 3D point verification</div><h2>Strut {selectedStrut.id} · {selectedStrut.classification}</h2><p>Support {(selectedStrut.support * 100).toFixed(1)}% · longest gap {selectedStrut.gap} samples. {selectedStrut.classification === "missing" ? "Verify the crosshair neighborhood across adjacent slices before calling this a missing strut." : selectedStrut.classification === "disconnected" ? "Verify whether the highlighted gap persists across adjacent slices and reaches both material segments." : "This strut is currently clear; review the X-ray crop if you need a manual confirmation."}</p><ol><li>Inspect this X-ray slice at the orange crosshair.</li><li>Move the CT slice slider above and compare adjacent neighborhoods.</li><li>Confirm with the registered graph endpoints before accepting or rejecting the candidate.</li></ol></div><img src={`http://127.0.0.1:8001/api/v1/part1/xray-neighborhood.png?x=${(selectedStrut.a[0] + selectedStrut.b[0]) / 2}&y=${(selectedStrut.a[1] + selectedStrut.b[1]) / 2}&z=${(selectedStrut.a[2] + selectedStrut.b[2]) / 2}`} alt={`X-ray neighborhood for selected strut ${selectedStrut.id}`}/></section>}
      </section>
      <aside className="analysis-panel"><div className="eyebrow">Saved detector run</div><h2>Inspection controls</h2><div className="filters"><label>CT Z slice <output>{slice} / 760</output><input type="range" min="0" max="760" value={slice} onChange={event => setSlice(Number(event.target.value))}/></label></div><div className="total"><span>Baseline accuracy</span><strong>Unavailable</strong><small>0% TIFF is not present locally, so no false-positive rate is claimed.</small></div><div className="copilot"><div className="eyebrow">Pipeline co-pilot</div><p>{chatAnswer}</p>{chatSources.length > 0 && <small>Sources: {chatSources.join(", ")}</small>}<form onSubmit={askCopilot}><input value={chatQuestion} onChange={event => setChatQuestion(event.target.value)} placeholder="Ask about this run"/><button type="submit">Ask</button></form></div><div className="metrics-panel"><div className="eyebrow">Classification metrics</div><p className="metrics-hint">Predicted labels are pulled live from the current run and refresh automatically after every run. No file in this project is adjudicated ground truth, so there is nothing to auto-load as truth. The saved run does have a second, differently-parameterized screening pass (per_strut_verdicts.json) — loading it below scores inter-method agreement, not detector accuracy.</p><form onSubmit={computeMetrics}><label>Predicted (y_pred) <small className="metrics-live">{metricsPredCount != null ? `${metricsPredCount.toLocaleString()} live from ${activeRunId ?? "saved run"}` : "loading..."}</small><textarea readOnly value={metricsPred} rows={3}/></label><label>Comparison (y_true) — not ground truth<textarea value={metricsTrue} onChange={event => setMetricsTrue(event.target.value)} rows={3} placeholder="paste matching-order labels here, or load the second-opinion pass below"/></label><button type="button" className="metrics-second-opinion" disabled={!secondOpinion} onClick={() => secondOpinion && setMetricsTrue(secondOpinion)}>{secondOpinion ? "Load second-opinion pass (per_strut_verdicts.json) as comparison" : "Second-opinion pass unavailable for this run"}</button><div className="metrics-row"><label>Average<select value={metricsAverage} onChange={event => setMetricsAverage(event.target.value as typeof metricsAverage)}><option value="binary">Binary</option><option value="macro">Macro</option><option value="weighted">Weighted</option></select></label>{metricsAverage === "binary" && <label>Positive label<input value={metricsPositive} onChange={event => setMetricsPositive(event.target.value)} placeholder="missing"/></label>}</div><button type="submit">Recompute now</button></form>{metricsError && <small className="metrics-error">{metricsError}</small>}{metricsResult && <div className="metrics-result"><div><span>Accuracy</span><strong>{(metricsResult.accuracy * 100).toFixed(1)}%</strong></div><div><span>Precision</span><strong>{(metricsResult.precision * 100).toFixed(1)}%</strong></div><div><span>Recall</span><strong>{(metricsResult.recall * 100).toFixed(1)}%</strong></div><div><span>F1</span><strong>{(metricsResult.f1 * 100).toFixed(1)}%</strong></div></div>}</div><p className="disclaimer">Counts shown above are saved robust-detector classes, not browser-side reclassification.</p></aside>
    </div>
  </main>;
}
