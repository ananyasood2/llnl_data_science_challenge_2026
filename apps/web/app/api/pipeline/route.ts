import { readFile } from "node:fs/promises";
import { join, resolve } from "node:path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const artifacts = resolve(process.cwd(), "../..", "output", "part2");

async function readJson(relativePath: string) {
  try {
    return JSON.parse(await readFile(join(artifacts, relativePath), "utf8"));
  } catch {
    return null;
  }
}

export async function GET() {
  const [inspection, inventory, repair] = await Promise.all([
    readJson("refined_registration_20260729/tube_r4_precision/inspection_summary.json"),
    readJson("metadata/inventory.json"),
    readJson("visual_repair_robust_v2/repair_summary.json"),
  ]);
  return Response.json({ inspection, inventory, repair });
}
