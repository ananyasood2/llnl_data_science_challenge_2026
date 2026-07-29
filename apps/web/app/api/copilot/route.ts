import { readFile } from "node:fs/promises";
import { join, resolve } from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const artifacts = resolve(process.cwd(), "../..", "output", "part2");

async function artifact(relativePath: string) {
  try { return JSON.parse(await readFile(join(artifacts, relativePath), "utf8")); } catch { return null; }
}

export async function POST(request: Request) {
  const { question = "", context } = await request.json() as { question?: string; context?: { slice?: number; visibleGroups?: Record<string, boolean>; run?: string } };
  const [inspection, inventory, repair] = await Promise.all([
    artifact("refined_registration_20260729/tube_r4_precision/inspection_summary.json"),
    artifact("metadata/inventory.json"),
    artifact("visual_repair_robust_v2/repair_summary.json"),
  ]);
  const query = question.toLowerCase();
  const sources: string[] = [];
  let answer: string;
  if ((query.includes("missing") || query.includes("disconnect")) && inspection) {
    const counts = inspection.counts;
    answer = `The retained radius-2 registered screen produced ${counts.missing_candidate.toLocaleString()} low-support candidates, ${counts.disconnected_candidate.toLocaleString()} discontinuity candidates, and ${counts.uncertain_candidate.toLocaleString()} intermediate-support candidates at threshold ${inspection.selected_threshold}. None are confirmed defects.`;
    sources.push("inspection_summary.json");
  } else if ((query.includes("repair") || query.includes("stiff") || query.includes("before")) && repair) {
    const restored = repair.repair?.restored_candidate_strut_count;
    const recovery = repair.mechanics_proxy?.estimated_stiffness_recovery_percent;
    answer = `The saved repair scenario restores ${restored?.toLocaleString?.() ?? "the flagged"} candidate struts. Its non-FEA relative-density/stiffness proxy estimates ${recovery?.toFixed?.(2) ?? "a saved"}% recovery; restoring every candidate is an upper-bound and may over-repair.`;
    sources.push("repair_summary.json");
  } else if ((query.includes("file") || query.includes("registered") || query.includes("data")) && inventory) {
    answer = inventory.summary ?? `The inventory records ${inventory.files?.length ?? "the available"} files. Only explicitly registered JSON-to-TIFF pairs are used for CT comparison; unregistered STLs require a registration task.`;
    sources.push("inventory.json");
  } else {
    answer = "I can answer from the saved inventory, registered screening summary, and repair summary. Ask about files, registration, missing/disconnected candidates, or before/after repair metrics.";
  }
  const visible = context?.visibleGroups ? Object.entries(context.visibleGroups).filter(([, value]) => value).map(([name]) => name) : [];
  const viewportNote = context?.slice !== undefined ? ` Current view context: slice ${context.slice}; visible layers: ${visible.join(", ") || "none"}; run: ${context.run ?? "saved run"}.` : "";
  return Response.json({ answer: `${answer}${viewportNote}`, sources });
}
