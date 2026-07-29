# Part 1 Deliverables

All Part 1 work is implemented on the `MdWaliullah` branch.

## Tasks 1-3: MCP tools

`src/mcp_server.py` exposes these FastMCP tools:

- `segment_ct_dataset(input_filepath, output_filepath, threshold)`
- `visualize_slice(input_filepath, output_filepath, slice_index, axis=0)`
- `skeletonize(input_filepath, output_filepath)`

The user-level Codex entry `mcp_servers.segmentation-tools` points to this repository's `src/mcp_server.py` and the Anaconda Python interpreter. Restart Codex before checking `/mcp` so it reloads the registration.

## Task 4: NDE report

The provided NDE skill is used by `src/nde_report.py`. The completed unit-cell report and its two required 3D views are in `output/part1/nde_report/`.

## Task 5: custom skill

`.agents/skills/threshold_optimizer/SKILL.md` defines a reusable threshold-comparison workflow. Its three unit-cell candidates and written selection are in `output/part1/threshold_optimizer/`.

## Task 6: segmentation subagent

`.codex/agents/segmentation_subagent.toml` defines the bounded specialist. The reproducible implementation is `src/segment_tiff_lattice.py`. Its real-dataset run created `data/9x9x9_octet_lattice/segmentation/`, containing the TIFF mask, slice 380, diagnostics, executed script copy, and report.

## Task 7: evaluation

`evals/rubric_segmentation_1.md` is the required image-comparison rubric. `evals/evaluation_segmentation_1.json` contains the result for the generated slice 380.

## Validation commands

```powershell
C:\Users\waliu\anaconda3\python.exe -m py_compile src\mcp_server.py src\nde_report.py src\segment_tiff_lattice.py
C:\Users\waliu\anaconda3\python.exe src\nde_report.py data\unitcell\unitcell.npy output\part1\unitcell_mask.npy output\part1\unitcell_skeleton.npy --output output\part1\nde_report
```
