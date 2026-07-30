# Measurement Service Guidance

- MCP wrappers must call `app.repositories.measurements` or
  `lattice_pipeline.measurements`; do not duplicate formulas in prompts or
  route handlers.
- Scientific tools accept context IDs and bounded scalar arguments only.
- Tool envelopes must include dataset ID, revision, tool run ID, scope,
  warnings, and provenance, and must exclude raw arrays and paths.
- A stale context is a `409`; missing data is `404`; missing qualified analysis
  prerequisites are `409`; invalid arguments are `422`.
- OpenAI is an optional tool-selection and narration layer. The deterministic
  measurement API and local orchestrator must remain functional without a key.
- Reports are immutable derivative artifacts under `MEASUREMENT_ARTIFACT_ROOT`.
