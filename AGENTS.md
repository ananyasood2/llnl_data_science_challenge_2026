# Lattice CT Copilot Repository Guidance

Treat the current dashboard, dataset intake, registered JSON workflow, and CT
pipeline as working baselines. Preserve their routes, commands, and existing
behavior while extending them.

- Keep scientific calculations deterministic and in `lattice_pipeline` or the
  FastAPI copilot tool layer. Language-model output may summarize tool results
  but must not create numerical findings.
- Never modify TIFF, NPY, JSON, STL, or registered source data. Write only
  derivative artifacts under the configured copilot artifact root.
- Pass dataset IDs, artifact IDs, context IDs, and element IDs across public
  boundaries; never expose server paths or raw CT arrays to browser/model code.
- Preserve XYZ public coordinates and ZYX NumPy indexing conventions.
- Validate API changes from `services/analysis-api` with
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`; validate web changes
  with `npm run typecheck:web` and `npm run lint:web`.
- Read the corresponding workflow in `copilot-guidance/skills/` before changing
  a copilot analysis behavior. Specialized developer-agent role definitions are
  in `copilot-guidance/agents/`.

