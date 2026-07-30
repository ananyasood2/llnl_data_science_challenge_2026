---
name: measurement-reporting
description: Create reproducible lattice CT measurement reports from cited thickness, relative-density, design-comparison, and lineage tool results. Use when asked to generate, export, download, or summarize a measurement or NDE report.
---

# Measurement Reporting

## Workflow

1. Call `create_measurement_context` when no valid `context_id` was supplied.
2. Verify the measurement context and analysis revision.
3. Obtain `get_thickness_summary`, `get_relative_density`, and `compare_measurements_to_design` results.
4. Call `create_measurement_report`; do not build report metrics in prose or code outside the deterministic service.
5. Return the approved artifact link and cite the report tool run.

## Required Content

- Dataset ID and analysis revision
- Target, critical, and user thickness cutoffs
- Eligible and excluded strut counts
- Thickness summary and percent-below results
- Segmented and enclosing volumes, ROI definition, and relative density
- Policy version, provisional status, warnings, and provenance

Only derivative JSON and Markdown artifacts may be created. Never modify source TIFF, NPY, JSON, or STL data.
