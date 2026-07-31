"""Measurement API and repository regression tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import numpy as np

from lattice_pipeline.cache import ANALYSIS_VERSION

from app.core.config import get_settings
from app.main import app
from app.repositories.measurements import MEASUREMENT_COMPATIBLE_ANALYSIS_VERSIONS


SELECTED_STRUT_THRESHOLDS = (
    "&target_thickness_um=350&critical_cutoff_um=300&user_cutoff_um=350"
)


def _fixture_dataset(root: Path) -> None:
    processed = root / "qualified_sample" / "processed"
    processed.mkdir(parents=True)
    mask = np.zeros((8, 8, 8), dtype=np.uint8)
    mask[1:7, 1:7, 1:7] = 1
    np.save(processed / "mask.npy", mask)
    analysis = {
        "meta": {
            "cache_fingerprint": "fixture-revision",
            "analysis_version": ANALYSIS_VERSION,
            "analysis_stride": 1,
            "voxel_size_mm": 0.1,
            "voxel_size_source": "test_fixture",
            "threshold": 0.5,
            "threshold_source": "manual",
            "unreliable_boundary_faces": [],
        },
        "struts": [
            {
                "id": 1,
                "status": "thin",
                "measured_thickness_um": 280.0,
                "design_thickness_um": 350.0,
                "thickness_ratio": 0.8,
                "node_a": 10,
                "node_b": 11,
                "polyline": [[1, 1, 1], [6, 6, 6]],
            },
            {
                "id": 2,
                "status": "healthy",
                "measured_thickness_um": 350.0,
                "design_thickness_um": 350.0,
                "thickness_ratio": 1.0,
                "node_a": 11,
                "node_b": 12,
                "polyline": [[1, 6, 1], [6, 1, 6]],
            },
            {
                "id": 3,
                "status": "thick",
                "measured_thickness_um": 420.0,
                "design_thickness_um": 350.0,
                "thickness_ratio": 1.2,
                "node_a": 12,
                "node_b": 13,
                "polyline": [[1, 1, 6], [6, 6, 1]],
            },
            {
                "id": 4,
                "status": "missing",
                "measured_thickness_um": None,
                "design_thickness_um": 350.0,
                "node_a": 13,
                "node_b": 14,
                "polyline": [[1, 6, 6], [6, 1, 1]],
            },
        ],
    }
    (processed / "analysis.json").write_text(json.dumps(analysis), encoding="utf-8")


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_measurement_summary_is_deterministic_and_contains_no_paths(tmp_path, monkeypatch) -> None:
    _fixture_dataset(tmp_path)
    monkeypatch.setenv("BUILTIN_DATA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        response = asyncio.run(
            _request(
                "GET",
                "/v1/datasets/qualified_sample/measurements"
                "?user_cutoff_um=360&include_map=true",
            )
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_revision"] == "fixture-revision"
    assert payload["thickness"]["eligible_strut_count"] == 3
    assert payload["thickness"]["below_user_cutoff"]["count"] == 2
    assert payload["relative_density"]["roi_definition"].startswith("registered_graph")
    assert payload["comparison"]["policy"]["provisional"] is True
    assert payload["thickness_map"]["element_count"] == 4
    serialized = json.dumps(payload).lower()
    assert str(tmp_path).lower() not in serialized
    assert "mask.npy" not in serialized


def test_outlier_and_sensitivity_endpoints(tmp_path, monkeypatch) -> None:
    _fixture_dataset(tmp_path)
    monkeypatch.setenv("BUILTIN_DATA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        outliers = asyncio.run(
            _request(
                "GET",
                "/v1/datasets/qualified_sample/measurements/outliers?cutoff_um=360&limit=1",
            )
        )
        sensitivity = asyncio.run(
            _request(
                "POST",
                "/v1/datasets/qualified_sample/measurements/cutoff-sensitivity",
                json={"cutoffs_um": [300, 350, 400]},
            )
        )
    finally:
        get_settings.cache_clear()

    assert outliers.status_code == 200
    assert outliers.json()["struts"][0]["strut_id"] == 1
    assert outliers.json()["truncated"] is True
    assert sensitivity.status_code == 200
    assert [item["count_below"] for item in sensitivity.json()["results"]] == [1, 1, 2]


def test_measurement_prerequisites_and_dataset_ids_are_guarded(tmp_path, monkeypatch) -> None:
    (tmp_path / "unqualified" / "processed").mkdir(parents=True)
    monkeypatch.setenv("BUILTIN_DATA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        missing_artifacts = asyncio.run(
            _request("GET", "/v1/datasets/unqualified/measurements")
        )
        path_attempt = asyncio.run(
            _request("GET", "/v1/datasets/..%2Fsecret/measurements")
        )
    finally:
        get_settings.cache_clear()

    assert missing_artifacts.status_code == 409
    assert path_attempt.status_code in {404, 422}


def test_selected_strut_endpoint_is_revision_qualified_and_typed(tmp_path, monkeypatch) -> None:
    _fixture_dataset(tmp_path)
    monkeypatch.setenv("BUILTIN_DATA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        response = asyncio.run(
            _request(
                "GET",
                "/v1/datasets/qualified_sample/measurements/struts/2"
                "?expected_analysis_revision=fixture-revision"
                "&target_thickness_um=350&critical_cutoff_um=300&user_cutoff_um=360",
            )
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_revision"] == "fixture-revision"
    assert payload["strut"]["strut_id"] == 2
    assert payload["strut"]["percentile"]["rank_percent"] == 66.667
    assert payload["strut"]["target_comparison"]["below"] is False
    assert payload["strut"]["user_cutoff_comparison"]["difference_um"] == -10.0
    assert payload["neighbors"]["total_count"] == 2
    assert payload["neighbors"]["median_thickness_um"] == 350.0
    assert payload["neighbors"]["selected_minus_median_um"] == 0.0
    serialized = json.dumps(payload).lower()
    assert "polyline" not in serialized
    assert str(tmp_path).lower() not in serialized


def test_selected_strut_errors_and_unmeasured_response(tmp_path, monkeypatch) -> None:
    _fixture_dataset(tmp_path)
    monkeypatch.setenv("BUILTIN_DATA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        missing_revision = asyncio.run(
            _request(
                "GET",
                "/v1/datasets/qualified_sample/measurements/struts/1"
                "?target_thickness_um=350&critical_cutoff_um=300&user_cutoff_um=350",
            )
        )
        missing_thresholds = asyncio.run(
            _request(
                "GET",
                "/v1/datasets/qualified_sample/measurements/struts/1"
                "?expected_analysis_revision=fixture-revision",
            )
        )
        stale_revision = asyncio.run(
            _request(
                "GET",
                "/v1/datasets/qualified_sample/measurements/struts/1"
                "?expected_analysis_revision=stale"
                + SELECTED_STRUT_THRESHOLDS,
            )
        )
        unknown = asyncio.run(
            _request(
                "GET",
                "/v1/datasets/qualified_sample/measurements/struts/999"
                "?expected_analysis_revision=fixture-revision"
                + SELECTED_STRUT_THRESHOLDS,
            )
        )
        unmeasured = asyncio.run(
            _request(
                "GET",
                "/v1/datasets/qualified_sample/measurements/struts/4"
                "?expected_analysis_revision=fixture-revision"
                + SELECTED_STRUT_THRESHOLDS,
            )
        )
    finally:
        get_settings.cache_clear()

    assert missing_revision.status_code == 422
    assert missing_thresholds.status_code == 422
    assert stale_revision.status_code == 409
    assert unknown.status_code == 404
    assert unmeasured.status_code == 200
    selected = unmeasured.json()["strut"]
    assert selected["measurement_eligible"] is False
    assert selected["percentile"]["rank_percent"] is None
    assert selected["target_comparison"]["below"] is None


def test_stale_analysis_version_requires_preprocessing(tmp_path, monkeypatch) -> None:
    _fixture_dataset(tmp_path)
    analysis_path = tmp_path / "qualified_sample" / "processed" / "analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["meta"]["analysis_version"] = min(MEASUREMENT_COMPATIBLE_ANALYSIS_VERSIONS) - 1
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    monkeypatch.setenv("BUILTIN_DATA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        response = asyncio.run(
            _request("GET", "/v1/datasets/qualified_sample/measurements")
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 409
    assert "npm run dev:structure -- --preprocess-only" in response.json()["detail"]


def test_version_7_remains_available_for_measurements_with_connectivity_warning(
    tmp_path, monkeypatch
) -> None:
    _fixture_dataset(tmp_path)
    analysis_path = tmp_path / "qualified_sample" / "processed" / "analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["meta"]["analysis_version"] = 7
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    monkeypatch.setenv("BUILTIN_DATA_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        response = asyncio.run(
            _request("GET", "/v1/datasets/qualified_sample/measurements")
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["provenance"]["analysis_version"] == 7
    assert any("legacy connectivity taxonomy" in warning for warning in payload["warnings"])


def test_openapi_exposes_measurement_contracts() -> None:
    schema = app.openapi()
    assert "/v1/datasets/{dataset_id}/measurements" in schema["paths"]
    assert "/v1/datasets/{dataset_id}/measurements/outliers" in schema["paths"]
    assert (
        "/v1/datasets/{dataset_id}/measurements/cutoff-sensitivity"
        in schema["paths"]
    )
    assert (
        "/v1/datasets/{dataset_id}/measurements/struts/{strut_id}"
        in schema["paths"]
    )
    parameters = schema["paths"][
        "/v1/datasets/{dataset_id}/measurements/struts/{strut_id}"
    ]["get"]["parameters"]
    required_query_names = {
        parameter["name"]
        for parameter in parameters
        if parameter["in"] == "query" and parameter.get("required")
    }
    assert required_query_names == {
        "expected_analysis_revision",
        "target_thickness_um",
        "critical_cutoff_um",
        "user_cutoff_um",
    }
