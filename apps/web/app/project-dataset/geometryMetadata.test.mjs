import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

async function importGeometryModule() {
  const sourcePath = new URL("./geometryMetadata.ts", import.meta.url);
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const outDir = join(tmpdir(), "lattice-web-tests");
  const outPath = join(outDir, `geometryMetadata-${Date.now()}.mjs`);
  await mkdir(outDir, { recursive: true });
  await writeFile(outPath, transpiled);
  return import(pathToFileURL(outPath).href);
}

test("formats STL metadata for the upload card", async () => {
  const {
    formatGeometryBounds,
    formatGeometryDimensions,
    formatGeometryNumber,
    formatStlFormat,
  } = await importGeometryModule();
  const metadata = {
    format: "stl-binary",
    triangle_count: 4,
    vertex_count: 4,
    dimensions: { x: 1, y: 2.5, z: 3.125 },
    bounds: { x: [0, 1], y: [-1.25, 1.25], z: [0, 3.125] },
  };

  assert.equal(formatStlFormat(metadata.format), "Binary STL");
  assert.equal(formatGeometryDimensions(metadata), "1 x 2.5 x 3.125");
  assert.equal(formatGeometryBounds(metadata), "x: 0 to 1; y: -1.25 to 1.25; z: 0 to 3.125");
  assert.equal(formatGeometryNumber(1 / 3), "0.333333");
});
