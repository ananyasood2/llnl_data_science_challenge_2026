# Analysis API

FastAPI orchestration service for the Multi-Agent Lattice CT Inspection
Dashboard.

The service provides dataset intake and analysis routes plus a registered
measurement repository, deterministic measurement endpoints, dataset-scoped
MCP tools, and a traceable Measurement Copilot runtime.

## Local development

From the repository root:

```bash
.venv/bin/python -m pip install -e .
.venv/bin/python -m pip install -r services/analysis-api/requirements-dev.txt
cd services/analysis-api
../../.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Installing the repository root separately makes the shared `lattice_pipeline`
package importable. Do not put a relative editable path in this service's
requirements file: pip resolves editable paths from the caller's working
directory, which is unreliable when this file is invoked from the repository
root.

Open `http://localhost:8000/health` or `http://localhost:8000/docs`.

Measurement endpoints include:

```text
GET  /v1/datasets/{dataset_id}/measurements
GET  /v1/datasets/{dataset_id}/measurements/outliers
POST /v1/datasets/{dataset_id}/measurements/cutoff-sensitivity
POST /v1/measurement-copilot/contexts
POST /v1/measurement-copilot/conversations/{conversation_id}/messages
GET  /v1/measurement-copilot/runs/{run_id}
GET  /v1/measurement-copilot/artifacts/{artifact_id}
```

Run the MCP server from the repository root with
`npm run dev:measurement-mcp`. It exposes only dataset/context-scoped tools and
never returns raw CT arrays or server paths.

Do not add scientific calculations to API route modules. Future implementations
must sit behind service interfaces and return validated Pydantic schemas.
