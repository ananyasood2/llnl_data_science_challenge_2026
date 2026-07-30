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
  const outDir = join(tmpdir(), "lattice-measurement-web-tests");
  const outPath = join(outDir, `${name}-${Date.now()}.mjs`);
  await mkdir(outDir, { recursive: true });
  await writeFile(outPath, transpiled);
  return import(pathToFileURL(outPath).href);
}

test("measurement formatting preserves units and status meaning", async () => {
  const formatting = await importModule(
    "./measurementFormatting.ts",
    "measurement-formatting",
  );

  assert.equal(formatting.formatMicrons(350), "350 µm");
  assert.equal(formatting.formatPercent(10.045), "10.05%");
  assert.equal(formatting.statusLabel("warn"), "Warning");
});

test("thickness colors use critical, target, and upper bands", async () => {
  const { thicknessColor, clampCutoff } = await importModule(
    "./measurementFormatting.ts",
    "measurement-colors",
  );

  assert.equal(thicknessColor(null, 300, 350), "#94a3b8");
  assert.equal(thicknessColor(280, 300, 350), "#dc2626");
  assert.equal(thicknessColor(325, 300, 350), "#f59e0b");
  assert.equal(thicknessColor(375, 300, 350), "#0f9f75");
  assert.equal(thicknessColor(500, 300, 350), "#7c3aed");
  assert.equal(clampCutoff(-5), 1);
  assert.equal(clampCutoff(5000), 2000);
});
