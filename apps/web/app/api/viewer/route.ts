import { readFile, readdir } from "node:fs/promises";
import { resolve } from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const root = resolve(process.cwd(), "../..");

type Candidate = { strut_id: number; material_fraction: number; longest_gap_samples: number; flag: "missing_candidate" | "disconnected_candidate" | "uncertain_candidate" | "clear" };

function candidatesFromCsv(text: string): Map<number, Candidate> {
  const [header, ...rows] = text.trim().split(/\r?\n/);
  const columns = header.split(",");
  return new Map(rows.map(row => {
    const values = row.split(",");
    const record = Object.fromEntries(columns.map((column, index) => [column, values[index]]));
    return [Number(record.strut_id), { strut_id: Number(record.strut_id), material_fraction: Number(record.material_fraction), longest_gap_samples: Number(record.longest_gap_samples), flag: record.flag as Candidate["flag"] }];
  }));
}

const secondOpinionLabel = (verdict: string): "missing" | "disconnected" | "clear" =>
  verdict === "missing" ? "missing" : verdict === "disconnected" ? "disconnected" : "clear";

export async function GET(request: Request) {
  const runId = new URL(request.url).searchParams.get("run");
  const uploadDir = runId && /^[a-zA-Z0-9_-]+$/.test(runId) ? resolve(root, "output", "uploads", runId) : null;
  const uploadFiles = uploadDir ? await readdir(uploadDir).catch(() => []) : [];
  const uploadedGraph = uploadDir && uploadFiles.find(name => name.endsWith(".json") && name !== "inspection_summary.json") ? resolve(uploadDir, uploadFiles.find(name => name.endsWith(".json") && name !== "inspection_summary.json")!) : null;
  const [graphText, candidateText, scaleText] = await Promise.all([
    readFile(uploadedGraph ?? resolve(root, "data/missing_struts/registered_jsons/210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.json"), "utf8"),
    readFile(resolve(root, "output/part2/refined_registration_20260729/tube_r4_precision/strut_candidates.csv"), "utf8"),
    readFile(resolve(root, "data/missing_struts/physical_scale.json"), "utf8"),
  ]);
  // Second opinion is only available for the fixed saved run: it comes from a differently-parameterized
  // screening pass (per_strut_verdicts.json), not from independently adjudicated ground truth.
  const secondOpinionText = uploadDir ? null : await readFile(resolve(root, "output/part2/registered_screen_20260728/per_strut_verdicts.json"), "utf8").catch(() => null);
  const secondOpinion = secondOpinionText
    ? new Map((JSON.parse(secondOpinionText) as { struts: Array<{ strut_id: number; verdict: string }> }).struts.map(entry => [entry.strut_id, secondOpinionLabel(entry.verdict)]))
    : null;
  const graph = JSON.parse(graphText) as { junctions: Array<{ id: number; position: number[] }>; struts: Array<{ id: number; junction0: number; junction1: number; thickness?: number }> };
  const candidates = candidatesFromCsv(candidateText);
  const nodes = new Map(graph.junctions.map(node => [node.id, node.position]));
  const struts = graph.struts.map(strut => {
    const candidate = candidates.get(strut.id);
    const support = candidate?.material_fraction ?? 1;
    const gap = candidate?.longest_gap_samples ?? 0;
    // Intermediate-support candidates remain visible in the data but are not rendered as defects.
    const classification = candidate?.flag === "missing_candidate" ? "missing" : candidate?.flag === "disconnected_candidate" ? "disconnected" : "clear";
    const confidence = classification === "clear" ? 1 : Math.max(.18, Math.min(1, classification === "missing" ? (0.04 - support) / .04 : gap / 31));
    return { id: strut.id, junction0: strut.junction0, junction1: strut.junction1, thickness: strut.thickness, a: nodes.get(strut.junction0), b: nodes.get(strut.junction1), classification, confidence, support, gap, second_opinion: secondOpinion?.get(strut.id) ?? null };
  });
  return Response.json({
    scale: JSON.parse(scaleText), nodes: graph.junctions.map(node => node.position), struts,
    secondOpinionAvailable: secondOpinion !== null,
    limitations: {
      diameter: "No per-strut diameter measurement is present in the current detection artifacts; tube radius uses centreline-support proxy and is labelled accordingly.",
      baseline_0_percent: "No 0% TIFF stack is present locally, so false-positive rate cannot be computed.",
      second_opinion: "second_opinion comes from a separately-parameterized image screening pass (per_strut_verdicts.json), not from adjudicated ground truth. Treat any score against it as inter-method agreement, not accuracy.",
    },
  });
}
