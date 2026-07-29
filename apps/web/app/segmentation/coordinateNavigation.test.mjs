import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import ts from "typescript";

async function importCoordinateNavigationModule() {
  const sourcePath = new URL("./coordinateNavigation.ts", import.meta.url);
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const outDir = join(tmpdir(), "lattice-web-tests");
  const outPath = join(outDir, `coordinateNavigation-${Date.now()}.mjs`);
  await mkdir(outDir, { recursive: true });
  await writeFile(outPath, transpiled);
  return import(outPath);
}

const datasetContext = {
  datasetId: "dataset-1",
  jobId: null,
  dataset: "Octet lattice",
  projectId: "project-1",
  dimensions: { x: "837", y: "815", z: "761" },
  voxelSizeMicron: "unknown",
  scaleUnit: "voxel",
};

test("derives inclusive voxel bounds from loaded dimensions", async () => {
  const { getVolumeBounds } = await importCoordinateNavigationModule();

  assert.deepEqual(getVolumeBounds(datasetContext), {
    x: 836,
    y: 814,
    z: 760,
  });
});

test("validates integer-only in-bounds voxel coordinates", async () => {
  const { validateVoxelCoordinateInput } = await importCoordinateNavigationModule();

  assert.deepEqual(
    validateVoxelCoordinateInput(
      { x: "836", y: "814", z: "760" },
      { x: 836, y: 814, z: 760 },
    ),
    {
      coordinate: { x: 836, y: 814, z: 760 },
      errors: {},
      valid: true,
    },
  );

  const invalid = validateVoxelCoordinateInput(
    { x: "12.5", y: "815", z: "" },
    { x: 836, y: 814, z: 760 },
  );

  assert.equal(invalid.valid, false);
  assert.equal(invalid.errors.x, "Use an integer voxel index.");
  assert.equal(invalid.errors.y, "Expected 0-814 voxels.");
  assert.equal(invalid.errors.z, "Required.");
});

test("chooses the active-axis slice for a selected coordinate", async () => {
  const { getSliceIndexForCoordinate } = await importCoordinateNavigationModule();
  const coordinate = { x: 11, y: 22, z: 33 };

  assert.equal(getSliceIndexForCoordinate("X", coordinate), 11);
  assert.equal(getSliceIndexForCoordinate("Y", coordinate), 22);
  assert.equal(getSliceIndexForCoordinate("Z", coordinate), 33);
});

test("projects marker position onto the active slice plane", async () => {
  const { getMarkerPosition } = await importCoordinateNavigationModule();
  const bounds = { x: 100, y: 200, z: 400 };
  const coordinate = { x: 25, y: 50, z: 100 };

  assert.deepEqual(getMarkerPosition("X", coordinate, bounds), {
    left: 25,
    top: 25,
  });
  assert.deepEqual(getMarkerPosition("Y", coordinate, bounds), {
    left: 25,
    top: 25,
  });
  assert.deepEqual(getMarkerPosition("Z", coordinate, bounds), {
    left: 25,
    top: 25,
  });
});
