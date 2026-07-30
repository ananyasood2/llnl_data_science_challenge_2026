# Dash Viewer Guidance

- Keep the Dash viewer authoritative for filters, bounds, camera, threshold,
  and selected element.
- Update `ViewportContextV1` whenever those values change. Use origin-restricted
  `postMessage` only for the parent-frame bridge.
- Reuse the existing evidence panel for raw CT review. Copilot actions select or
  highlight registered element IDs; they do not generate client-side science.

