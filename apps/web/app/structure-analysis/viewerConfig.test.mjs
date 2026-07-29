import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import ts from "typescript";

async function importConfigModule() {
  const sourcePath = new URL("./viewerConfig.ts", import.meta.url);
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const outDir = join(tmpdir(), "lattice-web-tests");
  const outPath = join(outDir, `viewerConfig-${Date.now()}.mjs`);
  await mkdir(outDir, { recursive: true });
  await writeFile(outPath, transpiled);
  return import(outPath);
}

test("structure viewer URL defaults to the local Dash dashboard", async () => {
  const { getStructureViewerUrl } = await importConfigModule();

  assert.equal(getStructureViewerUrl(undefined), "http://127.0.0.1:8050");
  assert.equal(getStructureViewerUrl("   "), "http://127.0.0.1:8050");
});

test("structure viewer URL can be configured by public environment value", async () => {
  const { getStructureViewerUrl } = await importConfigModule();

  assert.equal(getStructureViewerUrl("https://viewer.example.test"), "https://viewer.example.test");
});
