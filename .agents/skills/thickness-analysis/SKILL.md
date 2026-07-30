---
name: thickness-analysis
description: Analyze registered lattice strut thickness statistics, histograms, cutoff sensitivity, and out-of-spec rankings through deterministic measurement MCP tools. Use for questions about microns, thin or thick struts, 350/300 micron limits, user cutoffs, worst struts, or thickness-map highlighting.
---

# Thickness Analysis

Use deterministic tool output for every numerical claim.

## Workflow

1. Call `create_measurement_context` when no valid `context_id` was supplied; never accept a dataset path.
2. Call `get_measurement_context` and verify the qualified analysis revision.
3. Call `get_thickness_summary` for distribution statistics and eligibility counts.
4. Call `list_out_of_spec_struts` only when rankings or highlighting are relevant. Keep its limit at or below 50.
5. Call `analyze_measurement_sensitivity` for cutoff comparisons. State that it does not rerun CT segmentation.
6. Cite each result as `[tool_name:tool_run_id]`.

## Interpretation Rules

- Treat `measured_thickness_um` as a deterministic EDT-derived measurement, not an LLM estimate.
- Report eligible and excluded strut counts. Never convert missing thickness to zero.
- Distinguish the 350 µm target, 300 µm critical cutoff, and user cutoff.
- Preserve microns and the analysis revision.
- Describe pass/warn/fail as provisional unless an approved policy replaces `demo-policy-v1`.
- Return element IDs for map actions; do not return raw CT, arrays, or server paths.

Stop without a scientific conclusion if the required tool evidence is unavailable or stale.
