import { createWriteStream } from "node:fs";
import { mkdir, readFile } from "node:fs/promises";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import { join, resolve } from "node:path";
import { spawn } from "node:child_process";
import nodeProcess from "node:process";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const root = resolve(process.cwd(), "../..");
const safeName = (name: string) => name.replace(/[^a-zA-Z0-9._ -]/g, "_");

function runDetector(tiff: string, graph: string, output: string) {
  return new Promise<void>((resolveRun, rejectRun) => {
    const python: string = nodeProcess.env.LATTICE_PYTHON ?? "C:\\Users\\waliu\\anaconda3\\python.exe";
    const child = spawn(python, ["src/analyze_missing_struts.py", "--tiff", tiff, "--metadata", graph, "--output", output], { cwd: root });
    let error = "";
    child.stderr.on("data", (chunk: Buffer) => { error += chunk.toString(); });
    child.on("error", rejectRun);
    child.on("close", (code: number | null) => code === 0 ? resolveRun() : rejectRun(new Error(error || `Detector exited with code ${code}`)));
  });
}

export async function POST(request: Request) {
  const form = await request.formData();
  const tiff = form.get("tiff");
  const graph = form.get("json");
  const stl = form.get("stl");
  if (!(tiff instanceof File) || !(graph instanceof File)) return Response.json({ detail: "TIFF and registered JSON are required." }, { status: 400 });
  const runId = `upload_${new Date().toISOString().replace(/[:.]/g, "-")}`;
  const output = join(root, "output", "uploads", runId);
  await mkdir(output, { recursive: true });
  const save = async (file: File) => { const target = join(output, safeName(file.name)); await pipeline(Readable.fromWeb(file.stream() as never), createWriteStream(target)); return target; };
  const [tiffPath, graphPath] = await Promise.all([save(tiff), save(graph)]);
  const graphData = JSON.parse(await readFile(graphPath, "utf8"));
  const stemsMatch = tiff.name.replace(/\.(tif|tiff)$/i, "") === graph.name.replace(/\.json$/i, "");
  if (!stemsMatch || !Array.isArray(graphData.junctions) || !Array.isArray(graphData.struts)) {
    return Response.json({ detail: "Upload rejected: TIFF and JSON must have matching stems and a registered lattice-graph schema. Run registration first for other pairs." }, { status: 422 });
  }
  if (stl instanceof File) await save(stl);
  await runDetector(tiffPath, graphPath, output);
  return Response.json({ runId, output: `output/uploads/${runId}`, summary: `${`output/uploads/${runId}`}/inspection_summary.json`, stlStatus: stl instanceof File ? "Saved but excluded until registered." : "Not supplied." });
}
