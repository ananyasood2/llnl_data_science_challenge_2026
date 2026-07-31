"""Contract and orchestration tests for the measurement copilot."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from fastapi import HTTPException

from lattice_pipeline.cache import ANALYSIS_VERSION

from app.core.config import get_settings
from app.main import app
from app.measurement_copilot.contracts import MeasurementContextCreate
from app.measurement_copilot.mcp_server import mcp
from app.measurement_copilot.orchestrator import OPENAI_TOOLS, run_measurement_copilot
from app.measurement_copilot.store import measurement_context_store
from app.measurement_copilot.tools import TOOL_REGISTRY, create_measurement_context
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
                "design_thickness_um": 350.0,
                "thickness_ratio": thickness / 350,
                "node_a": index - 1,
                "node_b": index,
                "polyline": [[1, index, 1], [8, index, 8]],
            }
        )
    analysis = {
        "meta": {
            "cache_fingerprint": "agent-fixture-revision",
            "analysis_version": ANALYSIS_VERSION,
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


def test_context_creation_is_not_exposed_to_webpage_model() -> None:
    names = {tool["name"] for tool in OPENAI_TOOLS}
    assert "create_measurement_context" not in names


def test_mcp_context_entry_point_qualifies_dataset_and_defaults(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    try:
        created = create_measurement_context(dataset_id="agent_sample")
    finally:
        get_settings.cache_clear()

    assert created["context_id"].startswith("mctx_")
    assert created["dataset_id"] == "agent_sample"
    assert created["analysis_revision"] == "agent-fixture-revision"
    assert created["target_thickness_um"] == 350.0
    assert created["critical_cutoff_um"] == 300.0
    assert created["user_cutoff_um"] == 350.0
    assert created["target_density_percent"] == 10.0
    assert created["selected_strut_id"] is None
    assert created["visible_statuses"] == []
    assert "path" not in json.dumps(created).lower()


def test_mcp_context_entry_point_rejects_unknown_dataset(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    try:
        with pytest.raises(HTTPException) as error:
            create_measurement_context(dataset_id="not_registered")
    finally:
        get_settings.cache_clear()

    assert error.value.status_code == 404


def test_context_validates_and_canonicalizes_selected_strut(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    try:
        created = create_measurement_context(
            dataset_id="agent_sample",
            selected_strut_id="2",
        )
        selected = TOOL_REGISTRY["inspect_selected_strut"](
            context_id=created["context_id"]
        )
        with pytest.raises(HTTPException) as unknown_error:
            create_measurement_context(
                dataset_id="agent_sample",
                selected_strut_id=999,
            )
        with pytest.raises(HTTPException) as boolean_error:
            create_measurement_context(
                dataset_id="agent_sample",
                selected_strut_id=True,
            )
    finally:
        get_settings.cache_clear()

    assert created["selected_strut_id"] == 2
    assert selected["summary"]["strut"]["strut_id"] == 2
    assert selected["summary"]["strut"]["percentile"]["rank_percent"] == 40.0
    assert selected["summary"]["neighbors"]["total_count"] == 2
    assert selected["elements"][0]["element_role"] == "selected"
    assert {item["element_role"] for item in selected["elements"][1:]} == {"neighbor"}
    assert "shared endpoint" in " ".join(selected["warnings"]).lower()
    assert unknown_error.value.status_code == 404
    assert boolean_error.value.status_code == 422


def test_selected_strut_question_uses_context_only_tool_and_citation(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    try:
        context = create_measurement_context(
            dataset_id="agent_sample",
            selected_strut_id=2,
        )
        result = run_measurement_copilot(
            "How does this selected strut compare with its neighbors and where does it rank?",
            context["context_id"],
        )
    finally:
        get_settings.cache_clear()

    assert [item["tool_name"] for item in result["tool_results"]] == [
        "inspect_selected_strut"
    ]
    assert "[inspect_selected_strut:mtool_" in result["answer"]
    assert "persisted analysis status `thin`" in result["answer"]
    assert "below the 300.000 µm critical cutoff" in result["answer"]
    assert "below the active 350.000 µm user cutoff" in result["answer"]
    assert (
        "Of 2 registered shared-endpoint neighbors, 2 have eligible measured "
        "thickness and 0 are excluded."
        in result["answer"]
    )
    assert "median across the 2 measured neighbors" in result["answer"]
    assert "analysis revision `agent-fixtur`" in result["answer"]
    assert "topology only" in result["answer"].lower()
    assert result["viewer_actions"] == [{"type": "highlight_struts", "strut_ids": [2]}]


def test_mcp_context_drives_all_measurement_evidence_tools(tmp_path, monkeypatch) -> None:
    _configure(tmp_path, monkeypatch)
    try:
        context = create_measurement_context(
            dataset_id="agent_sample",
            user_cutoff_um=325.0,
        )
        results = [
            TOOL_REGISTRY[name](context_id=context["context_id"])
            for name in (
                "get_measurement_context",
                "get_thickness_summary",
                "list_out_of_spec_struts",
                "get_relative_density",
                "compare_measurements_to_design",
                "analyze_measurement_sensitivity",
                "create_measurement_report",
            )
        ]
    finally:
        get_settings.cache_clear()

    assert [result["tool_name"] for result in results] == [
        "get_measurement_context",
        "get_thickness_summary",
        "list_out_of_spec_struts",
        "get_relative_density",
        "compare_measurements_to_design",
        "analyze_measurement_sensitivity",
        "create_measurement_report",
    ]
    assert {result["analysis_revision"] for result in results} == {
        "agent-fixture-revision"
    }
    serialized = json.dumps(results).lower()
    assert str(tmp_path).lower() not in serialized
    assert "mask.npy" not in serialized


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


def test_openai_selected_strut_answer_requires_actual_tool_run_citation(
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
                            name="inspect_selected_strut",
                            arguments=json.dumps({"context_id": "mctx_untrusted"}),
                            call_id="call_fixture",
                        )
                    ],
                    output_text="",
                )
            tool_output = next(
                item
                for item in kwargs["input"]
                if isinstance(item, dict)
                and item.get("type") == "function_call_output"
            )
            tool_result = json.loads(tool_output["output"])
            citation = (
                f"[inspect_selected_strut:{tool_result['tool_run_id']}]"
            )
            return SimpleNamespace(
                output=[],
                output_text=f"Selected-strut evidence is available {citation}.",
            )

    class FakeOpenAI:
        def __init__(self, api_key):
            assert api_key == "test-key-not-sent"
            self.responses = FakeResponses()

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    try:
        context = create_measurement_context(
            dataset_id="agent_sample",
            selected_strut_id=2,
        )
        context_id = context["context_id"]
        result = run_measurement_copilot(
            "Analyze this selected strut.",
            context_id,
        )
    finally:
        get_settings.cache_clear()

    assert result["mode"] == "openai-tool-calling"
    assert result["tool_results"][0]["context_id"] == context_id
    tool_result = result["tool_results"][0]
    assert tool_result["tool_name"] == "inspect_selected_strut"
    assert (
        f"[inspect_selected_strut:{tool_result['tool_run_id']}]"
        in result["answer"]
    )
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


def test_openai_selected_strut_with_wrong_citation_uses_deterministic_answer(
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
                            name="inspect_selected_strut",
                            arguments=json.dumps({"context_id": "mctx_untrusted"}),
                            call_id="call_fixture",
                        )
                    ],
                    output_text="",
                )
            return SimpleNamespace(
                output=[],
                output_text=(
                    "Selected-strut evidence is available "
                    "[inspect_selected_strut:mtool_fabricated]."
                ),
            )

    class FakeOpenAI:
        def __init__(self, api_key):
            assert api_key == "test-key-not-sent"
            self.responses = FakeResponses()

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    try:
        context = create_measurement_context(
            dataset_id="agent_sample",
            selected_strut_id=2,
        )
        result = run_measurement_copilot(
            "Analyze this selected strut and its neighbors.",
            context["context_id"],
        )
    finally:
        get_settings.cache_clear()

    tool_result = result["tool_results"][0]
    actual_citation = (
        f"[inspect_selected_strut:{tool_result['tool_run_id']}]"
    )
    assert result["mode"] == "openai-tool-calling"
    assert tool_result["tool_name"] == "inspect_selected_strut"
    assert actual_citation in result["answer"]
    assert "mtool_fabricated" not in result["answer"]
    assert "topology only" in result["answer"].lower()
    assert any(
        "exact citation" in warning.lower()
        and "deterministic narration" in warning.lower()
        for warning in result["warnings"]
    )


def test_openai_selected_strut_with_wrong_tool_runs_required_inspection(
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
            tool_output = next(
                item
                for item in kwargs["input"]
                if isinstance(item, dict)
                and item.get("type") == "function_call_output"
            )
            tool_result = json.loads(tool_output["output"])
            return SimpleNamespace(
                output=[],
                output_text=(
                    "Thickness evidence is available "
                    f"[get_thickness_summary:{tool_result['tool_run_id']}]."
                ),
            )

    class FakeOpenAI:
        def __init__(self, api_key):
            assert api_key == "test-key-not-sent"
            self.responses = FakeResponses()

    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    try:
        context = create_measurement_context(
            dataset_id="agent_sample",
            selected_strut_id=2,
        )
        result = run_measurement_copilot(
            "Analyze this selected strut.",
            context["context_id"],
        )
    finally:
        get_settings.cache_clear()

    assert [item["tool_name"] for item in result["tool_results"]] == [
        "inspect_selected_strut"
    ]
    tool_result = result["tool_results"][0]
    assert (
        f"[inspect_selected_strut:{tool_result['tool_run_id']}]"
        in result["answer"]
    )
    assert "topology only" in result["answer"].lower()
    assert any(
        "selected-strut evidence" in warning.lower()
        and "deterministic narration" in warning.lower()
        for warning in result["warnings"]
    )
