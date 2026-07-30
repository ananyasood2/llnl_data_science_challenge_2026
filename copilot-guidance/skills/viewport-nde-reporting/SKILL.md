---
name: viewport-nde-reporting
description: Create a reproducible NDE report scoped to the active lattice CT viewport. Use when asked to export, summarize, or generate a viewport-scoped engineering report.
---

# Viewport NDE Reporting

1. Require an active, non-stale viewport context.
2. Call `create_nde_report`; it includes deterministic defect and connectivity
   findings, scope, revision, and provenance.
3. Return the controlled report artifact link and explain its exact viewport
   scope. Do not include raw CT data or mutate source files.

