import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import ts from "typescript";

async function importFormattingModule() {
  const sourcePath = new URL("./analysisFormatting.ts", import.meta.url);
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const outDir = join(tmpdir(), "lattice-web-tests");
  const outPath = join(outDir, `analysisFormatting-${Date.now()}.mjs`);
  await mkdir(outDir, { recursive: true });
  await writeFile(outPath, transpiled);
  return import(outPath);
}

test("unknown voxel scale remains labeled pixels and voxels", async () => {
  const { formatVoxelSize } = await importFormattingModule();

  assert.equal(
    formatVoxelSize({ scaleUnit: "voxel", voxelSizeMicron: "unknown" }),
    "Unknown; distances remain in pixels/voxels",
  );
  assert.equal(
    formatVoxelSize({ scaleUnit: "micron", voxelSizeMicron: "" }),
    "Unknown; distances remain in pixels/voxels",
  );
  assert.equal(
    formatVoxelSize({ scaleUnit: "micron", voxelSizeMicron: "25.4" }),
    "25.4 micron",
  );
});

test("formats backend analysis job states for the UI", async () => {
  const { formatAnalysisStatus } = await importFormattingModule();

  assert.equal(formatAnalysisStatus("queued"), "Queued");
  assert.equal(formatAnalysisStatus("segmenting"), "Segmenting");
  assert.equal(formatAnalysisStatus("skeletonizing"), "Skeletonizing");
  assert.equal(formatAnalysisStatus("complete"), "Complete");
  assert.equal(formatAnalysisStatus("failed"), "Failed");
});
