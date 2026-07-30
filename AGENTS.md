# Lattice CT Measurement Workflow Guidance

Preserve the working intake, CT preparation, registered viewer, defect workflow,
and existing commands while extending the application.

- Keep every scientific calculation in `src/lattice_pipeline` or the FastAPI
  deterministic repository/tool layer. Language-model prompts may select and
  explain tools but must not create numerical findings.
- Never modify source TIFF, NPY, JSON, or STL data. Write only derivative
  reports and trace records under the configured measurement artifact root.
- Pass dataset IDs, context IDs, analysis revisions, tool run IDs, artifact IDs,
  and element IDs across public boundaries. Never expose server paths or raw CT
  arrays to browsers or models.
- Preserve XYZ public coordinates and ZYX NumPy indexing.
- Treat `demo-policy-v1` pass/warn/fail results as provisional, not as an
  approved engineering acceptance decision.
- Read the relevant workflow in `.agents/skills/` before changing a
  measurement-agent behavior. Executable Codex role definitions are in
  `.codex/agents/`.
- Validate Python changes with
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` from
  `services/analysis-api`, and web changes with `npm run typecheck:web`,
  `npm run lint:web`, and `npm run test:web`.
