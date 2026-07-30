---
name: relative-density-analysis
description: Analyze segmented material volume, registered enclosing volume, computed lattice relative density, and comparison with the 10 percent design target through deterministic MCP tools. Use for density, material-volume, ROI, porosity-adjacent, or design-volume questions.
---

# Relative Density Analysis

## Workflow

1. Call `get_measurement_context` and verify the dataset and analysis revision.
2. Call `get_relative_density` for segmented volume, enclosing volume, density, target, and ROI definition.
3. Call `compare_measurements_to_design` when a pass/warn/fail comparison is requested.
4. Cite each numerical statement as `[tool_name:tool_run_id]`.

## Interpretation Rules

- Define relative density as segmented material volume divided by the named registered ROI volume.
- State the ROI definition and segmentation-threshold caveat.
- Preserve `mm³`, percent, percentage-point difference, and revision fields.
- Do not infer mechanical performance or porosity from relative density alone.
- Treat `demo-policy-v1` as provisional and not scientist-approved.
- Never request or expose raw masks, CT arrays, or filesystem paths.

Stop and report the prerequisite error when voxel spacing, segmentation, or registered geometry is unqualified.
