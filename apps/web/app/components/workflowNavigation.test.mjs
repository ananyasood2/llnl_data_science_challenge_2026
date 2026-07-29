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

test("marks only the active workflow step as the current page", async () => {
  const { getWorkflowStepAriaCurrent } = await importModule(
    "./workflowNavigation.ts",
    "workflowNavigation-active",
  );

  assert.equal(getWorkflowStepAriaCurrent("active"), "page");
  assert.equal(getWorkflowStepAriaCurrent("completed"), undefined);
  assert.equal(getWorkflowStepAriaCurrent("available"), undefined);
  assert.equal(getWorkflowStepAriaCurrent("locked"), undefined);
});

test("keeps locked workflow steps non-navigable", async () => {
  const { isWorkflowStepNavigable } = await importModule(
    "./workflowNavigation.ts",
    "workflowNavigation-locked",
  );

  assert.equal(
    isWorkflowStepNavigable({
      id: "structure-analysis",
      href: "/structure-analysis?datasetId=dataset-123",
      state: "locked",
    }),
    false,
  );
  assert.equal(
    isWorkflowStepNavigable({
      id: "structure-analysis",
      href: "/structure-analysis?datasetId=dataset-123",
      state: "available",
    }),
    true,
  );
  assert.equal(
    isWorkflowStepNavigable({
      id: "segmentation",
      href: null,
      state: "available",
    }),
    false,
  );
});

test("preserves analysis query parameters between preparation and structure pages", async () => {
  const { buildWorkflowHref } = await importModule(
    "./workflowNavigation.ts",
    "workflowNavigation-query",
  );
  const params = new URLSearchParams(
    "projectId=proj-9&datasetId=dataset-123&jobId=job-456&dataset=part-a&x=128&y=129&z=130&scaleUnit=micron&voxelSizeMicron=12.5&threshold=0.42&foregroundVoxelCount=1200&backgroundVoxelCount=3400",
  );

  assert.equal(
    buildWorkflowHref("/structure-analysis", params),
    "/structure-analysis?projectId=proj-9&datasetId=dataset-123&jobId=job-456&dataset=part-a&x=128&y=129&z=130&scaleUnit=micron&voxelSizeMicron=12.5&threshold=0.42&foregroundVoxelCount=1200&backgroundVoxelCount=3400",
  );
  assert.equal(
    buildWorkflowHref("/segmentation", params),
    "/segmentation?projectId=proj-9&datasetId=dataset-123&jobId=job-456&dataset=part-a&x=128&y=129&z=130&scaleUnit=micron&voxelSizeMicron=12.5&threshold=0.42&foregroundVoxelCount=1200&backgroundVoxelCount=3400",
  );
});
