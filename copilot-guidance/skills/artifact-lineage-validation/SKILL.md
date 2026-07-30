---
name: artifact-lineage-validation
description: Validate provenance and reproducibility of lattice CT copilot results. Use when reviewing a copilot run, report artifact, context fingerprint, analysis revision, or scientific traceability.
---

# Artifact Lineage Validation

1. Retrieve the run or report artifact by its controlled ID.
2. Verify dataset ID, context fingerprint, threshold, registered coordinate
   space, bounds, graph/analysis revision, cited tool results, and timestamps.
3. Flag a mismatch or stale context instead of inferring continuity across runs.
4. Confirm outputs contain element IDs and artifact links—not raw CT arrays or
   server filesystem paths.

