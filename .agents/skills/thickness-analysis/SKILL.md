---
name: thickness-analysis
description: Analyze registered lattice strut thickness statistics, selected-strut percentiles and immediate topology neighbors, histograms, cutoff sensitivity, and out-of-spec rankings through deterministic measurement MCP tools. Use for questions about a Strut ID, selected strut, microns, thin or thick struts, 350/300 micron limits, user cutoffs, worst struts, or thickness-map highlighting.
---

# Thickness Analysis

Use deterministic tool output for every numerical claim.

## Workflow

1. Call `create_measurement_context` when no valid `context_id` was supplied; never accept a dataset path.
2. Call `get_measurement_context` and verify the qualified analysis revision.
3. Call `inspect_selected_strut` for a selected-Strut-ID question. Require the selection in the immutable context.
4. Call `get_thickness_summary` for distribution statistics and eligibility counts.
5. Call `list_out_of_spec_struts` only when rankings or highlighting are relevant. Keep its limit at or below 50.
6. Call `analyze_measurement_sensitivity` for cutoff comparisons. State that it does not rerun CT segmentation.
7. Cite each result as `[tool_name:tool_run_id]`.

## Interpretation Rules

- Treat `measured_thickness_um` as a deterministic EDT-derived measurement, not an LLM estimate.
- Report eligible and excluded strut counts. Never convert missing thickness to zero.
- Distinguish the 350 µm target, 300 µm critical cutoff, and user cutoff.
- Preserve microns and the analysis revision.
- Keep the persisted defect classification separate from target and cutoff comparisons.
- Analysis version 7 is qualified only for persisted thickness/density measurements. Preserve its legacy classification label, surface the compatibility warning, and make no connectivity conclusion from it.
- Treat neighbors as one-hop registered struts sharing an endpoint. Do not call a strut isolated or spatially clustered from this comparison alone.
- Describe pass/warn/fail as provisional unless an approved policy replaces `demo-policy-v1`.
- Return element IDs for map actions; do not return raw CT, arrays, or server paths.

Stop without a scientific conclusion if the required tool evidence is unavailable or stale.
