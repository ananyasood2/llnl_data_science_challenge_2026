"""Defect detection route tests."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO

import httpx
import numpy as np
import pytest
import tifffile
from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def _upload_storage_root(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_STORAGE_ROOT", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    yield tmp_path / "uploads"
    get_settings.cache_clear()


def _npy_bytes(array: np.ndarray) -> bytes:
    buffer = BytesIO()
    np.save(buffer, array)
    return buffer.getvalue()


def _tiff_bytes(array: np.ndarray) -> bytes:
    buffer = BytesIO()
    tifffile.imwrite(buffer, array)
    return buffer.getvalue()


def _graph_bytes() -> bytes:
    return json.dumps(
        {
            "junctions": [
                {"id": 0, "position": [1, 3, 3]},
                {"id": 1, "position": [6, 3, 3]},
            ],
            "struts": [{"id": 7, "junction0": 0, "junction1": 1}],
        }
    ).encode("utf-8")


async def _post_intake(
    slot: str,
    files: list[tuple[str, bytes, str]],
    *,
    dataset_id: str | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    data = {"slot": slot}
    if dataset_id:
        data["dataset_id"] = dataset_id
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/v1/datasets/intake",
            data=data,
            files=[
                ("files", (file_name, contents, content_type))
                for file_name, contents, content_type in files
            ],
        )


async def _client_request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def _prepare_dataset(upload_storage_root, *, graph: bool = True) -> str:
    volume = np.zeros((8, 8, 8), dtype=np.float32)
    response = asyncio.run(
        _post_intake(
            "npyVolume",
            [("volume.npy", _npy_bytes(volume), "application/octet-stream")],
        )
    )
    dataset_id = response.json()["dataset_id"]
    dataset_dir = upload_storage_root / dataset_id
    np.save(dataset_dir / "segmentation.npy", np.zeros_like(volume, dtype=bool))
    np.save(dataset_dir / "skeleton.npy", np.zeros_like(volume, dtype=bool))
    if graph:
        graph_response = asyncio.run(
            _post_intake(
                "graphJson",
                [("registered.json", _graph_bytes(), "application/json")],
                dataset_id=dataset_id,
            )
        )
        assert graph_response.json()["dataset_id"] == dataset_id
    return dataset_id


def test_tiff_graph_analysis_defect_detection_keeps_reference_available(
    _upload_storage_root,
) -> None:
    volume = np.zeros((8, 8, 8), dtype=np.uint16)
    volume[3, 1:7, 1:7] = 100
    tiff_response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [("sample.tif", _tiff_bytes(volume), "image/tiff")],
        )
    )
    assert tiff_response.status_code == 200
    dataset_id = tiff_response.json()["dataset_id"]

    graph_response = asyncio.run(
        _post_intake(
            "graphJson",
            [("registered.json", _graph_bytes(), "application/json")],
            dataset_id=dataset_id,
        )
    )
    assert graph_response.status_code == 200
    assert graph_response.json()["dataset_id"] == dataset_id
    assert graph_response.json()["graph_reference_available"] is True
    assert graph_response.json()["graph_reference_file_name"] == "registered.json"
    assert (_upload_storage_root / dataset_id / "registered.json").is_file()
    manifest = json.loads(
        (_upload_storage_root / dataset_id / "dataset_manifest.json").read_text()
    )
    assert manifest["graph_reference_available"] is True
    assert manifest["graph_reference_file_name"] == "registered.json"

    analysis = asyncio.run(
        _client_request(
            "POST",
            f"/v1/datasets/{dataset_id}/analysis-jobs",
            json={"dataset_name": "sample.tif"},
        )
    )
    assert analysis.status_code == 200
    analysis_payload = analysis.json()
    assert analysis_payload["dataset_id"] == dataset_id
    assert analysis_payload["artifacts"]["registered_graph"] == {
        "path": "registered.json"
    }

    artifact_manifest = asyncio.run(
        _client_request("GET", f"/v1/datasets/{dataset_id}/artifacts")
    )
    assert artifact_manifest.status_code == 200
    artifact_payload = artifact_manifest.json()
    assert artifact_payload["dataset_id"] == dataset_id
    assert artifact_payload["graph_reference_available"] is True
    assert artifact_payload["graph_reference_file_name"] == "registered.json"

    defect = asyncio.run(
        _client_request("POST", f"/v1/datasets/{dataset_id}/defect-jobs")
    )
    assert defect.status_code == 200
    defect_payload = defect.json()
    assert defect_payload["status"] == "complete"
    assert defect_payload["dataset_id"] == dataset_id
    assert defect_payload["reference_available"] is True
    assert "registered.json" in defect_payload["reference_message"]


def test_defect_job_creation_completion_and_persistence(_upload_storage_root) -> None:
    dataset_id = _prepare_dataset(_upload_storage_root)

    response = asyncio.run(
        _client_request("POST", f"/v1/datasets/{dataset_id}/defect-jobs")
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    assert payload["category_counts"]["missing"] == 1
    dataset_dir = _upload_storage_root / dataset_id
    assert (dataset_dir / "defects.json").is_file()
    assert (dataset_dir / "defect_summary.json").is_file()
    assert (dataset_dir / "defect_job.json").is_file()


def test_defect_slices_return_png_for_all_axes(_upload_storage_root) -> None:
    dataset_id = _prepare_dataset(_upload_storage_root)
    asyncio.run(_client_request("POST", f"/v1/datasets/{dataset_id}/defect-jobs"))

    for axis, index in [("x", 4), ("y", 3), ("z", 3)]:
        response = asyncio.run(
            _client_request(
                "GET",
                f"/v1/datasets/{dataset_id}/defect-slices/{axis}/{index}",
                params={"opacity": 0.7},
            )
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.headers["x-view"] == "defects"
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_reference_absent_reports_failed_without_fabricating_results(_upload_storage_root) -> None:
    dataset_id = _prepare_dataset(_upload_storage_root, graph=False)

    response = asyncio.run(
        _client_request("POST", f"/v1/datasets/{dataset_id}/defect-jobs")
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert not payload["reference_available"]
    assert "unavailable" in payload["reference_message"]
    assert not (_upload_storage_root / dataset_id / "defects.json").exists()


def test_lost_graph_association_reports_recorded_artifact_missing(
    _upload_storage_root,
) -> None:
    dataset_id = _prepare_dataset(_upload_storage_root)
    dataset_dir = _upload_storage_root / dataset_id
    _ = asyncio.run(
        _client_request(
            "POST",
            f"/v1/datasets/{dataset_id}/analysis-jobs",
            json={"dataset_name": "volume.npy"},
        )
    )
    (dataset_dir / "registered.json").unlink()

    response = asyncio.run(
        _client_request("POST", f"/v1/datasets/{dataset_id}/defect-jobs")
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["reference_available"] is False
    assert "recorded for this dataset but the file is missing" in payload["error"]
    assert payload["reference_message"] == payload["error"]


def test_not_run_and_no_defects_are_distinct(_upload_storage_root) -> None:
    dataset_id = _prepare_dataset(_upload_storage_root)
    latest = asyncio.run(
        _client_request("GET", f"/v1/datasets/{dataset_id}/defect-jobs/latest")
    )
    assert latest.json()["status"] == "not_run"

    healthy = np.zeros((8, 8, 8), dtype=bool)
    healthy[3, 1:7] = True
    np.save(_upload_storage_root / dataset_id / "segmentation.npy", healthy)
    np.save(_upload_storage_root / dataset_id / "skeleton.npy", healthy)
    complete = asyncio.run(
        _client_request("POST", f"/v1/datasets/{dataset_id}/defect-jobs")
    )
    assert complete.json()["status"] == "complete"
    assert complete.json()["total_flagged_elements"] == 0
    assert complete.json()["category_counts"] == {}


def test_failed_job_when_artifacts_missing(_upload_storage_root) -> None:
    response = asyncio.run(
        _post_intake(
            "npyVolume",
            [("volume.npy", _npy_bytes(np.zeros((4, 4, 4))), "application/octet-stream")],
        )
    )
    dataset_id = response.json()["dataset_id"]

    failed = asyncio.run(
        _client_request("POST", f"/v1/datasets/{dataset_id}/defect-jobs")
    )

    assert failed.json()["status"] == "failed"
    assert "Segmentation and skeleton" in failed.json()["error"]


def test_voxel_probe_includes_defect_category(_upload_storage_root) -> None:
    dataset_id = _prepare_dataset(_upload_storage_root)
    asyncio.run(_client_request("POST", f"/v1/datasets/{dataset_id}/defect-jobs"))

    response = asyncio.run(
        _client_request(
            "POST",
            f"/v1/datasets/{dataset_id}/voxel-probe",
            json={"threshold": 0.5, "x": 1, "y": 3, "z": 3},
        )
    )

    assert response.status_code == 200
    assert response.json()["defect_status"] == "flagged"
    assert response.json()["defect_category"] == "missing"
