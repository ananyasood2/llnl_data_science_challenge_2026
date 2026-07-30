import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

async function importModule(relativePath, name) {
  const sourcePath = new URL(relativePath, import.meta.url);
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const outDir = join(tmpdir(), "lattice-web-tests");
  const outPath = join(outDir, `${name}-${Date.now()}.mjs`);
  await mkdir(outDir, { recursive: true });
  await writeFile(outPath, transpiled);
  return import(pathToFileURL(outPath).href);
}

test("builds structure analysis handoff URL while preserving useful query params", async () => {
  const { buildStructureAnalysisHref } = await importModule(
    "./structureHandoff.ts",
    "structureHandoff",
  );

  const href = buildStructureAnalysisHref(
    {
      datasetId: "dataset-123",
      scaleUnit: "micron",
      voxelSizeMicron: "12.5",
    },
    {
      threshold: 0.42,
      foreground_voxel_count: 1200,
      background_voxel_count: 3400,
    },
    new URLSearchParams("dataset=part-a&projectId=proj-9&obsolete=kept"),
  );

  assert.equal(
    href,
    "/structure-analysis?dataset=part-a&projectId=proj-9&obsolete=kept&datasetId=dataset-123&scaleUnit=micron&threshold=0.42&foregroundVoxelCount=1200&backgroundVoxelCount=3400&voxelSizeMicron=12.5",
  );
});

test("does not build structure analysis href without saved segmentation artifacts", async () => {
  const { buildStructureAnalysisHref } = await importModule(
    "./structureHandoff.ts",
    "structureHandoff-empty",
  );

  assert.equal(
    buildStructureAnalysisHref(
      { datasetId: "dataset-123", scaleUnit: "voxel", voxelSizeMicron: "unknown" },
      null,
    ),
    null,
  );
});
