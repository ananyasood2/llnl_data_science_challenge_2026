---
name: viewport-connectivity-analysis
description: Analyze lattice connectivity for the current registered 3D dashboard viewport. Use when asked about connectivity, disconnected components, or the region currently visible in the lattice CT viewer.
---

# Viewport Connectivity Analysis

1. Require a current `context_id`; call `get_viewport_context` first when scope
   or selection is unclear.
2. Call `analyze_connectivity` and, for component questions,
   `get_disconnected_components`.
3. Report only returned metrics and element IDs. State that the result is scoped
   to displayed XYZ bounds and active filters.
4. Use a viewer highlight action for returned disconnected struts. Do not alter
   the dataset, threshold, or source graph.

