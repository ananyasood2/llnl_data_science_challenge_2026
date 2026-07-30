# Analysis API Guidance

- Keep existing `/v1/datasets` contracts backward compatible.
- The copilot API validates and stores viewport context before tool execution.
- Reuse `app/copilot/tools.py` from HTTP, MCP, and orchestration code; do not
  duplicate connectivity, defect, evidence, or geometry calculations in prompts.
- Copilot tools are read-only over source data and may write only report/run
  artifacts to `copilot_artifact_root`.
- Return compact structured data, bounded element pages, controlled artifact
  links, warnings, and provenance. Do not return raw arrays or filesystem paths.

