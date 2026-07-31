import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

async function importHelpers(name) {
  const sourcePath = new URL("./selectedStrutHelpers.ts", import.meta.url);
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

test("strut IDs are normalized without allowing route delimiters", async () => {
  const { normalizeStrutId } = await importHelpers("selected-strut-id");

  assert.equal(normalizeStrutId("  strut-17:A  "), "strut-17:A");
  assert.equal(normalizeStrutId("42"), "42");
  assert.equal(normalizeStrutId(""), null);
  assert.equal(normalizeStrutId("../42"), null);
  assert.equal(normalizeStrutId("42?revision=other"), null);
  assert.equal(normalizeStrutId("a".repeat(129)), null);
});

test("CT evidence href carries only public selection lineage", async () => {
  const { buildStrutEvidenceHref } = await importHelpers("selected-strut-href");

  assert.equal(
    buildStrutEvidenceHref("missing struts", "revision/7", "strut:42"),
    "/structure-analysis?datasetId=missing+struts&analysisRevision=revision%2F7&elementKind=strut&elementId=strut%3A42",
  );
});

test("the selected-strut Copilot question is fixed and cautious", async () => {
  const { SELECTED_STRUT_COPILOT_QUESTION } = await importHelpers(
    "selected-strut-question",
  );

  assert.match(SELECTED_STRUT_COPILOT_QUESTION, /deterministic thickness evidence/);
  assert.match(SELECTED_STRUT_COPILOT_QUESTION, /qualified analysis revision/);
  assert.match(SELECTED_STRUT_COPILOT_QUESTION, /population percentile/);
  assert.match(SELECTED_STRUT_COPILOT_QUESTION, /immediate one-hop topology neighbors/);
  assert.match(SELECTED_STRUT_COPILOT_QUESTION, /do not infer spatial isolation or clustering/);
  assert.match(SELECTED_STRUT_COPILOT_QUESTION, /do not make an engineering acceptance decision/);
});

test("Copilot context lineage requires the exact selected revision", async () => {
  const { analysisRevisionsMatch } = await importHelpers(
    "selected-strut-context-revision",
  );

  assert.equal(analysisRevisionsMatch("revision-7", "revision-7"), true);
  assert.equal(analysisRevisionsMatch("revision-7", "revision-8"), false);
  assert.equal(analysisRevisionsMatch("", ""), false);
});

test("histogram selection distinguishes visible, overflow, and unmeasured values", async () => {
  const { getSelectedHistogramMarker } = await importHelpers(
    "selected-strut-marker",
  );

  assert.deepEqual(getSelectedHistogramMarker(null, 400), { kind: "unmeasured" });
  assert.deepEqual(getSelectedHistogramMarker(360, 400), {
    kind: "visible",
    position: 0.9,
    valueUm: 360,
  });
  assert.deepEqual(getSelectedHistogramMarker(450, 400), {
    kind: "overflow",
    position: 1,
    valueUm: 450,
  });
});
