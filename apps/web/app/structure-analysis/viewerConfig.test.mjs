import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
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
  return import(pathToFileURL(outPath).href);
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

test("evidence parameters are bounded to the safe deep-link contract", async () => {
  const { parseStructureEvidenceParams } = await importConfigModule();

  assert.deepEqual(
    parseStructureEvidenceParams({
      datasetId: "missing_struts",
      analysisRevision: "567458c7f129",
      elementKind: "strut",
      elementId: "1284",
      ignored: "not-forwarded",
    }),
    {
      datasetId: "missing_struts",
      analysisRevision: "567458c7f129",
      elementKind: "strut",
      elementId: "1284",
    },
  );

  assert.deepEqual(
    parseStructureEvidenceParams({
      datasetId: ["missing_struts", "unitcell"],
      analysisRevision: "revision with spaces",
      elementKind: "beam",
      elementId: "<script>",
    }),
    {},
  );
});

test("ordinary dataset context does not become an incomplete evidence request", async () => {
  const { getStructureViewerUrl, parseStructureEvidenceParams } = await importConfigModule();
  const evidence = parseStructureEvidenceParams({ datasetId: "missing_struts" });

  assert.deepEqual(evidence, {});
  assert.equal(
    getStructureViewerUrl("https://viewer.example.test/dashboard", evidence),
    "https://viewer.example.test/dashboard",
  );
  assert.equal(
    getStructureViewerUrl("https://viewer.example.test/dashboard", {
      datasetId: "missing_struts",
    }),
    "https://viewer.example.test/dashboard",
  );
});

test("evidence parameters are forwarded to Dash with the evidence anchor", async () => {
  const { getStructureViewerUrl, parseStructureEvidenceParams } = await importConfigModule();
  const evidence = parseStructureEvidenceParams({
    datasetId: "missing_struts",
    analysisRevision: "567458c7f129",
    elementKind: "strut",
    elementId: "1284",
  });
  const configured = getStructureViewerUrl(
    "https://viewer.example.test/dashboard?theme=dark",
    evidence,
  );
  const viewerUrl = new URL(configured);

  assert.equal(viewerUrl.searchParams.get("theme"), "dark");
  assert.equal(viewerUrl.searchParams.get("datasetId"), "missing_struts");
  assert.equal(viewerUrl.searchParams.get("analysisRevision"), "567458c7f129");
  assert.equal(viewerUrl.searchParams.get("elementKind"), "strut");
  assert.equal(viewerUrl.searchParams.get("elementId"), "1284");
  assert.equal(viewerUrl.hash, "#evidence-panel");
});
