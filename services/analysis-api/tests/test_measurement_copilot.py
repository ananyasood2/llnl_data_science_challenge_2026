"""Contract and orchestration tests for the measurement copilot."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np

from app.core.config import get_settings
from app.main import app
from app.measurement_copilot.contracts import MeasurementContextCreate
from app.measurement_copilot.mcp_server import mcp
from app.measurement_copilot.orchestrator import run_measurement_copilot
from app.measurement_copilot.store import measurement_context_store
from app.measurement_copilot.tools import TOOL_REGISTRY
from app.repositories.measurements import measurement_repository


def _fixture_dataset(root: Path) -> None:
    processed = root / "agent_sample" / "processed"
    processed.mkdir(parents=True)
    mask = np.zeros((10, 10, 10), dtype=np.uint8)
    mask[1:9, 1:9, 1:9] = 1
    np.save(processed / "mask.npy", mask)
    records = []
    for index, thickness in enumerate([270.0, 290.0, 340.0, 360.0, 420.0], start=1):
        records.append(
            {
                "id": index,
                "status": "thin" if thickness < 350 else "healthy",
                "measured_thickness_um": thickness,
                "thickness_ratio": thickness / 350,
                "polyline": [[1, index, 1], [8, index, 8]],
            }
        )
    analysis = {
        "meta": {
            "cache_fingerprint": "agent-fixture-revision",
            "analysis_version": 7,
            "analysis_stride": 1,
            "voxel_size_mm": 0.1,
            "voxel_size_source": "test_fixture",
            "threshold": 0.5,
            "threshold_source": "manual",
            "unreliable_boundary_faces": [],
        },
        "struts": records,
    }
    (processed / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")


def _configure(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "data"
    artifact_root = tmp_path / "artifacts"
    _fixture_dataset(data_root)
    monkeypatch.setenv("BUILTIN_DATA_ROOT", str(data_root))
    monkeypatch.setenv("MEASUREMENT_ARTIFACT_ROOT", str(artifact_root))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()


def _context_id() -> str:
    payload = MeasurementContextCreate(
        dataset_id="agent_sample",
        target_thickness_um=350,
        critical_cutoff_um=300,
        user_cutoff_um=350,
        target_density_percent=10,
    )
    return measurement_context_store.put(
        payload,
        measurement_repository.revision("agent_sample"),
    ).context_id


def test_mcp_registers_all_dataset_scoped_measurement_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert names == set(TOOL_REGISTRY)


def test_broad_question_routes_both_specialists_and_highlights_outliers(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    try:
        result = run_measurement_copilot(
            "Does this print match the intended structure statistically? Highlight the ten worst struts.",
            _context_id(),
        )
    finally:
        get_settings.cache_clear()

    names = [item["tool_name"] for item in result["tool_results"]]
    assert names == [
        "get_thickness_summary",
        "get_relative_density",
        "compare_measurements_to_design",
        "list_out_of_spec_struts",
    ]
    specialists = {item["specialist"] for item in result["tool_results"]}
    assert "Thickness Analysis Agent" in specialists
    assert "Relative Density Agent" in specialists
    assert result["mode"] == "deterministic-local-orchestrator"
    assert result["viewer_actions"][0]["type"] == "highlight_struts"
    assert "provisional" in result["answer"].lower()
    assert "mtool_" in result["answer"]
    serialized = json.dumps(result).lower()
    assert str(tmp_path).lower() not in serialized
    assert "mask.npy" not in serialized


def test_report_tool_writes_only_derivative_artifacts(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    try:
        context_id = _context_id()
        result = run_measurement_copilot("Generate a measurement report.", context_id)
        report_result = next(
            item for item in result["tool_results"] if item["tool_name"] == "create_measurement_report"
        )
        artifact_id = report_result["summary"]["artifact_id"]
        artifact_root = get_settings().measurement_artifact_root
        assert (artifact_root / "reports" / f"{artifact_id}.json").is_file()
        assert (artifact_root / "reports" / f"{artifact_id}.md").is_file()
        repeated = run_measurement_copilot("Generate a measurement report.", context_id)
        repeated_report = next(
            item
            for item in repeated["tool_results"]
            if item["tool_name"] == "create_measurement_report"
        )
        assert repeated_report["summary"]["artifact_id"] == artifact_id
    finally:
        get_settings.cache_clear()


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_context_chat_and_run_endpoints_preserve_lineage(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    try:
        context_response = asyncio.run(
            _request(
                "POST",
                "/v1/measurement-copilot/contexts",
                json={"dataset_id": "agent_sample", "user_cutoff_um": 325},
            )
        )
        assert context_response.status_code == 200
        context = context_response.json()
        chat_response = asyncio.run(
            _request(
                "POST",
                "/v1/measurement-copilot/conversations/mconv_test/messages",
                json={
                    "context_id": context["context_id"],
                    "message": "What is the thickness distribution and show the worst struts?",
                },
            )
        )
        assert chat_response.status_code == 200
        run = chat_response.json()
        assert run["analysis_revision"] == context["analysis_revision"]
        stored_response = asyncio.run(
            _request("GET", f"/v1/measurement-copilot/runs/{run['run_id']}")
        )
        assert stored_response.status_code == 200
        assert stored_response.json() == run
    finally:
        get_settings.cache_clear()


def test_stale_context_is_rejected(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    try:
        context_id = _context_id()
        analysis_path = (
            get_settings().builtin_data_root / "agent_sample" / "processed" / "analysis.json"
        )
        payload = json.loads(analysis_path.read_text(encoding="utf-8"))
        payload["meta"]["cache_fingerprint"] = "new-revision"
        analysis_path.write_text(json.dumps(payload), encoding="utf-8")
        result = asyncio.run(
            _request(
                "POST",
                "/v1/measurement-copilot/conversations/mconv_stale/messages",
                json={"context_id": context_id, "message": "Analyze thickness."},
            )
        )
    finally:
        get_settings.cache_clear()

    assert result.status_code == 409


def test_openai_responses_loop_executes_registered_tools_without_trusting_model_scope(
    tmp_path,
    monkeypatch,
) -> None:
    _configure(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-sent")
    get_settings.cache_clear()
    observed_requests = []

    class FakeResponses:
        def create(self, **kwargs):
            observed_requests.append(kwargs)
            if len(observed_requests) == 1:
                return SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="get_thickness_summary",
                            arguments=json.dumps({"context_id": "mctx_untrusted"}),
                            call_id="call_fixture",
                        )
                    ],
                    output_text="",
                )
            return SimpleNamespace(
                output=[],
                output_text=(
                    "Thickness evidence is available "
                    "[get_thickness_summary:mtool_fixture]."
                ),
            )

    class FakeOpenAI:
        def __init__(self, api_key):
            assert api_key == "test-key-not-sent"
            self.responses = FakeResponses()

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    try:
        context_id = _context_id()
        result = run_measurement_copilot("Analyze thickness.", context_id)
    finally:
        get_settings.cache_clear()

    assert result["mode"] == "openai-tool-calling"
    assert result["tool_results"][0]["context_id"] == context_id
    assert observed_requests[0]["model"] == "gpt-5.6-terra"
    assert observed_requests[0]["reasoning"] == {"effort": "medium"}
    assert observed_requests[0]["tools"]
    outputs = observed_requests[1]["input"]
    assert any(
        isinstance(item, dict)
        and item.get("type") == "function_call_output"
        and item.get("call_id") == "call_fixture"
        for item in outputs
    )
