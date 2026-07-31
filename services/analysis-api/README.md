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
GET  /v1/datasets/{dataset_id}/measurements/struts/{strut_id}
POST /v1/datasets/{dataset_id}/measurements/cutoff-sensitivity
POST /v1/measurement-copilot/contexts
POST /v1/measurement-copilot/conversations/{conversation_id}/messages
GET  /v1/measurement-copilot/runs/{run_id}
GET  /v1/measurement-copilot/artifacts/{artifact_id}
```

The service-only MCP launcher can be inspected with
`npm run dev:measurement-mcp`. Codex itself is registered against the unified
`src/mcp_server.py`, which exposes the original Part 1 tools plus these service
tools. `create_measurement_context` is the dataset-scoped entry point;
`inspect_selected_strut` reads its Strut ID only from that immutable context,
and the remaining measurement tools also require the returned context ID. They
never return raw CT arrays or server paths.

If an analysis artifact predates the current scientific version, the service
returns an actionable `409`. Requalify the ignored derivative from the
repository root with `npm run dev:structure -- --preprocess-only`; compatible
volume arrays are retained.

Do not add scientific calculations to API route modules. Future implementations
must sit behind service interfaces and return validated Pydantic schemas.
