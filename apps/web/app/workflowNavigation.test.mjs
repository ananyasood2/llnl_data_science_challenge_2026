import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
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
  return import(outPath);
}

test("default workflow route sends root traffic to project dataset", async () => {
  const { defaultWorkflowRoute } = await importModule(
    "./workflowNavigation.ts",
    "workflowNavigation-default",
  );
  const pageSource = await readFile(new URL("./page.tsx", import.meta.url), "utf8");

  assert.equal(defaultWorkflowRoute, "/project-dataset");
  assert.match(pageSource, /redirect\(defaultWorkflowRoute\)/);
});

test("workflow navigation exposes three clickable routes", async () => {
  const { workflowNavItems } = await importModule(
    "./workflowNavigation.ts",
    "workflowNavigation-items",
  );

  assert.deepEqual(
    workflowNavItems.map((item) => [item.label, item.route]),
    [
      ["Project / Dataset", "/project-dataset"],
      ["CT Preparation", "/segmentation"],
      ["3D Structure Analysis", "/structure-analysis"],
    ],
  );
  assert.equal(
    workflowNavItems.some((item) => "disabled" in item || "locked" in item),
    false,
  );
});

test("workflow navigation highlights the current page", async () => {
  const { getActiveWorkflowItem } = await importModule(
    "./workflowNavigation.ts",
    "workflowNavigation-active",
  );

  assert.equal(getActiveWorkflowItem("/project-dataset").label, "Project / Dataset");
  assert.equal(getActiveWorkflowItem("/segmentation").label, "CT Preparation");
  assert.equal(
    getActiveWorkflowItem("/structure-analysis").label,
    "3D Structure Analysis",
  );
});

test("workflow hrefs preserve current dataset and threshold query context", async () => {
  const { buildWorkflowHref } = await importModule(
    "./workflowNavigation.ts",
    "workflowNavigation-query",
  );

  assert.equal(
    buildWorkflowHref(
      "/structure-analysis",
      "dataset=part-a&datasetId=dataset-123&threshold=0.42",
    ),
    "/structure-analysis?dataset=part-a&datasetId=dataset-123&threshold=0.42",
  );
  assert.equal(buildWorkflowHref("/segmentation", ""), "/segmentation");
});

test("CT preparation shows the associated graph JSON filename", async () => {
  const pageSource = await readFile(
    new URL("./segmentation/SegmentationClient.tsx", import.meta.url),
    "utf8",
  );
  const routeSource = await readFile(
    new URL("./segmentation/page.tsx", import.meta.url),
    "utf8",
  );
  const intakeSource = await readFile(
    new URL("./project-dataset/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(routeSource, /graphReference: getParam\(params, "graphReference"/);
  assert.match(intakeSource, /params\.set\("graphReference", graphReferenceFileName\)/);
  assert.match(pageSource, /<dt>Graph reference<\/dt>/);
  assert.match(pageSource, /analysisJob\?\.artifacts\?\.registered_graph\?\.path/);
});

test("no-context pages show CT empty state and 3D missing_struts fallback", async () => {
  const segmentationSource = await readFile(
    new URL("./segmentation/page.tsx", import.meta.url),
    "utf8",
  );
  const structureSource = await readFile(
    new URL("./structure-analysis/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(segmentationSource, /if \(!datasetContext\.datasetId\)/);
  assert.match(segmentationSource, /Choose dataset/);
  assert.match(segmentationSource, /href="\/project-dataset"/);
  assert.match(structureSource, /missing_struts/);
  assert.match(structureSource, /usingDefaultDataset/);
});
