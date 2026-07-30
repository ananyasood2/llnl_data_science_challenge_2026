import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import ts from "typescript";

async function importViewModesModule() {
  const sourcePath = new URL("./viewModes.ts", import.meta.url);
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const outDir = join(tmpdir(), "lattice-web-tests");
  const outPath = join(outDir, `viewModes-${Date.now()}.mjs`);
  await mkdir(outDir, { recursive: true });
  await writeFile(outPath, transpiled);
  return import(outPath);
}

test("CT preparation primary tabs match the requested workflow", async () => {
  const { primaryViewModes, segmentationComparisonModes } =
    await importViewModesModule();

  assert.deepEqual(
    primaryViewModes.map((mode) => mode.label),
    ["Original", "Segmentation", "Skeleton", "Defects"],
  );
  assert.deepEqual(
    segmentationComparisonModes.map((mode) => mode.label),
    ["Overlay", "Mask"],
  );
});

test("defects view uses the dedicated defect slice endpoint path", async () => {
  const { getDefectsEmptyStateMessage, getSliceFetchView } =
    await importViewModesModule();

  assert.equal(getSliceFetchView("defects"), null);
  assert.match(
    getDefectsEmptyStateMessage(),
    /unavailable until the defect-detection agent runs/i,
  );
});

test("defect tab state copy distinguishes job states", async () => {
  const { getDefectDetectionStateCopy } = await importViewModesModule();

  assert.equal(getDefectDetectionStateCopy("not_run").title, "Defect detection not run");
  assert.equal(getDefectDetectionStateCopy("running").title, "Defect detection running");
  assert.equal(getDefectDetectionStateCopy("complete").title, "No defects were found");
  assert.equal(
    getDefectDetectionStateCopy("failed", "classifier failed").message,
    "classifier failed",
  );
});

test("skeleton view fetches the persisted skeleton slice endpoint", async () => {
  const { getSliceFetchView } = await importViewModesModule();

  assert.equal(getSliceFetchView("skeleton"), "skeleton");
  assert.equal(getSliceFetchView("segmentation", "overlay"), "original");
  assert.equal(getSliceFetchView("segmentation", "mask"), "segmentation");
});
