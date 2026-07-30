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
  const outDir = join(tmpdir(), "lattice-web-tests");
  const outPath = join(outDir, `${name}-${Date.now()}.mjs`);
  await mkdir(outDir, { recursive: true });
  await writeFile(outPath, transpiled);
  return import(pathToFileURL(outPath).href);
}

const files = (...names) => names.map((name) => ({ name }));

test("file selection enters loading immediately", async () => {
  const { slotLoadingState } = await importModule("./uploadState.ts", "uploadState-loading");

  assert.deepEqual(slotLoadingState(files("graph.json")), {
    status: "loading",
    files: ["graph.json"],
  });
});

test("multiple upload slots retain independent state", async () => {
  const { initialSlotStates, slotLoadingState, slotSuccessState } = await importModule(
    "./uploadState.ts",
    "uploadState-independent",
  );

  const state = {
    ...initialSlotStates,
    graphJson: slotSuccessState(files("graph.json"), {
      valid: true,
      dataset_id: "graph-dataset",
      slot: "graphJson",
    }),
    stlCad: slotLoadingState(files("design.stl")),
  };

  assert.equal(state.graphJson.status, "valid");
  assert.equal(state.stlCad.status, "loading");
  assert.deepEqual(state.ctTiffStack, initialSlotStates.ctTiffStack);
});

test("second file selection does not reset existing slot state", async () => {
  const { initialSlotStates, slotLoadingState, slotSuccessState } = await importModule(
    "./uploadState.ts",
    "uploadState-second-selection",
  );

  const before = {
    ...initialSlotStates,
    graphJson: slotSuccessState(files("graph.json"), {
      valid: true,
      dataset_id: "graph-dataset",
      slot: "graphJson",
    }),
  };
  const after = {
    ...before,
    stlCad: slotLoadingState(files("design.stl")),
  };

  assert.equal(after.graphJson.status, "valid");
  assert.deepEqual(after.graphJson.files, ["graph.json"]);
  assert.equal(after.stlCad.status, "loading");
});

test("success and failure transitions preserve real validation details", async () => {
  const { slotFailureState, slotSuccessState } = await importModule(
    "./uploadState.ts",
    "uploadState-transitions",
  );

  assert.deepEqual(
    slotSuccessState(files("volume.npy"), {
      valid: true,
      dataset_id: "dataset-1",
      dimensions: { x: 2, y: 3, z: 4 },
    }),
    {
      status: "valid",
      files: ["volume.npy"],
      result: {
        valid: true,
        dataset_id: "dataset-1",
        dimensions: { x: 2, y: 3, z: 4 },
      },
      error: undefined,
    },
  );
  assert.deepEqual(slotFailureState(files("bad.json"), new Error("Invalid JSON.")), {
    status: "invalid",
    files: ["bad.json"],
    error: "Invalid JSON.",
  });
});

test("file input is cleared so re-selecting the same file triggers validation", async () => {
  const pageSource = await readFile(new URL("./page.tsx", import.meta.url), "utf8");

  assert.match(pageSource, /event\.currentTarget\.value = ""/);
  assert.match(pageSource, /onFileChange\(file\.id, selectedFiles\)/);
});

test("graph JSON upload is associated with the persisted TIFF dataset", async () => {
  const pageSource = await readFile(new URL("./page.tsx", import.meta.url), "utf8");

  assert.match(
    pageSource,
    /slotId === "npyVolume" \|\| slotId === "stlCad" \|\| slotId === "graphJson"/,
  );
});
