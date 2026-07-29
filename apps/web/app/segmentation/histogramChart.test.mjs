import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import ts from "typescript";

async function importHistogramChartModule() {
  const sourcePath = new URL("./histogramChart.ts", import.meta.url);
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const outDir = join(tmpdir(), "lattice-web-tests");
  const outPath = join(outDir, `histogramChart-${Date.now()}.mjs`);
  await mkdir(outDir, { recursive: true });
  await writeFile(outPath, transpiled);
  return import(outPath);
}

test("clamps threshold marker positions to the normalized intensity axis", async () => {
  const { getThresholdPercent } = await importHistogramChartModule();

  assert.equal(getThresholdPercent(-0.25), 0);
  assert.equal(getThresholdPercent(0.611), 61.1);
  assert.equal(getThresholdPercent(1.5), 100);
});

test("builds an area path scaled to the largest histogram bin", async () => {
  const { getHistogramPath } = await importHistogramChartModule();

  assert.equal(
    getHistogramPath([0, 5, 10], 300, 100),
    "M0,100 L0,100 L100.00,100.00 L200.00,50.00 L300.00,0.00 L300,100 Z",
  );
});

test("formats voxel counts and percentages for chart labels", async () => {
  const { formatPercent, formatVoxelCount } = await importHistogramChartModule();

  assert.equal(formatVoxelCount(1234567), "1,234,567");
  assert.equal(formatVoxelCount(null), "Pending");
  assert.equal(formatPercent(4.321), "4.32%");
  assert.equal(formatPercent(null), "Pending");
});

