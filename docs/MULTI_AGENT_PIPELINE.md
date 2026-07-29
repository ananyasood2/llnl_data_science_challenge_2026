# Coordinated Missing-Strut Pipeline

The pipeline uses bounded agents with durable handoffs rather than a flat toolset:

1. `data_explorer_agent` writes `output/pipeline/metadata/inventory.{json,md}`.
2. `defect_detection_agent` consumes that inventory and writes per-dataset artifacts below `output/pipeline/detection/` only for registered CT/graph pairs.
3. `visual_reasoner_agent` consumes detection outputs and writes reviewed renders below `output/pipeline/visual/`.
4. `repair_solver_agent` consumes reviewed candidates and writes a non-destructive repair proposal below `output/pipeline/repair/`.
5. `dashboard_serve_agent` reads saved artifacts only, rendering available stages and grounding every chat response in a cited artifact path.

Agent definitions live in `.codex/agents/`. Each definition has a narrow ownership boundary, retry limit, and output contract. Unregistered STL files create an explicit registration task; they are never silently compared to CT data. Automated flags remain candidates until validation.

Evaluate runs with [rubric_missing_struts.md](../evals/rubric_missing_struts.md). The initial scored evidence artifact is [evaluation_missing_struts_registered_0point5dash1.json](../evals/evaluation_missing_struts_registered_0point5dash1.json).
