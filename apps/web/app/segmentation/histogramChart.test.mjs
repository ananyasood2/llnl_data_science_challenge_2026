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

test("builds a log-scaled histogram path without changing raw bin labels", async () => {
  const { getHistogramDisplayCounts, getScaledHistogramPath } =
    await importHistogramChartModule();

  assert.deepEqual(getHistogramDisplayCounts([0, 9, 99], "log"), [0, 1, 2]);
  assert.equal(
    getScaledHistogramPath([0, 9, 99], 300, 100, "log"),
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

test("warns when foreground percentage is implausible or threshold is sensitive", async () => {
  const { getSegmentationQualityWarnings } = await importHistogramChartModule();

  const warnings = getSegmentationQualityWarnings({
    dataset_id: "dataset-1",
    scope: "volume",
    axis: null,
    index: null,
    bin_edges: [0, 0.25, 0.5, 0.75, 1],
    bin_counts: [10, 950, 30, 10],
    threshold: 0.5,
    foreground_voxel_count: 1,
    background_voxel_count: 999,
    foreground_percentage: 0.1,
    background_percentage: 99.9,
  });

  assert.deepEqual(warnings, [
    "Foreground is below 0.1%; threshold may be missing material.",
    "Threshold is sensitive; nearby histogram bins contain at least 5% of voxels.",
  ]);
});

test("returns no quality warnings for stable foreground and low nearby-bin mass", async () => {
  const { getSegmentationQualityWarnings } = await importHistogramChartModule();

  assert.deepEqual(
    getSegmentationQualityWarnings({
      dataset_id: "dataset-1",
      scope: "slice",
      axis: "z",
      index: 128,
      bin_edges: [0, 0.25, 0.5, 0.75, 1],
      bin_counts: [960, 10, 10, 20],
      threshold: 0.5,
      foreground_voxel_count: 30,
      background_voxel_count: 970,
      foreground_percentage: 3,
      background_percentage: 97,
    }),
    [],
  );
});
