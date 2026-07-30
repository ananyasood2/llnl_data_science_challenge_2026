---
name: measurement-lineage-validation
description: Validate lattice measurement tool outputs, units, dataset scope, analysis revisions, bounded element lists, artifact lineage, and absence of raw arrays or server paths. Use when reviewing measurement correctness, reproducibility, MCP contracts, reports, or agent claims.
---

# Measurement Lineage Validation

## Checks

1. Require one dataset ID, context ID, analysis revision, tool version, and tool run ID.
2. Verify all combined results use the same analysis revision and targets.
3. Verify thickness uses µm and volume uses mm³; reject ambiguous units.
4. Confirm excluded thickness values are reported and not treated as zero.
5. Confirm relative density names its registered ROI and segmentation caveat.
6. Confirm pass/warn/fail names its policy version and provisional state.
7. Confirm element lists are bounded and contain IDs rather than raw geometry arrays when entering model context.
8. Reject filesystem paths, raw CT/mask arrays, unsupported causal claims, and uncited numerical statements.
9. Confirm reports are derivative artifacts and source data remained unchanged.

Return a compact pass/fail checklist with the exact missing evidence. Do not repair or recalculate scientific results during validation.
