"""Dataset slice preview route tests."""

from __future__ import annotations

import asyncio
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


async def _post_intake(
    slot: str,
    files: list[tuple[str, bytes, str]],
    *,
    dataset_id: str | None = None,
    expected_dimensions: dict[str, int] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    multipart_files = [
        ("files", (file_name, contents, content_type))
        for file_name, contents, content_type in files
    ]

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        data = {"slot": slot}
        if dataset_id:
            data["dataset_id"] = dataset_id
        if expected_dimensions:
            data.update(
                {
                    f"expected_{axis}": str(value)
                    for axis, value in expected_dimensions.items()
                }
            )

        return await client.post(
            "/v1/datasets/intake",
            data=data,
            files=multipart_files,
        )


async def _get_slice(
    dataset_id: str,
    axis: str,
    index: int,
    view: str = "original",
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(
            f"/v1/datasets/{dataset_id}/slices/{axis}/{index}",
            params={"view": view},
        )


def _npy_bytes(array: np.ndarray) -> bytes:
    buffer = BytesIO()
    np.save(buffer, array)
    return buffer.getvalue()


def _tiff_bytes(array: np.ndarray) -> bytes:
    buffer = BytesIO()
    tifffile.imwrite(buffer, array)
    return buffer.getvalue()


def _assert_png_response(response: httpx.Response) -> None:
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert response.content.endswith(b"IEND\xaeB`\x82")


def test_original_slice_returns_png_for_npy_dataset() -> None:
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "volume.npy",
                    _npy_bytes(np.arange(24, dtype=np.float32).reshape((2, 3, 4))),
                    "application/octet-stream",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]

    slice_response = asyncio.run(_get_slice(dataset_id, "z", 1))

    _assert_png_response(slice_response)
    assert slice_response.headers["x-slice-axis"] == "z"
    assert slice_response.headers["x-slice-index"] == "1"
    assert slice_response.headers["x-view"] == "original"


def test_original_slice_returns_png_for_tiff_dataset() -> None:
    intake_response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [
                (
                    "stack.tif",
                    _tiff_bytes(np.arange(24, dtype=np.uint16).reshape((2, 3, 4))),
                    "image/tiff",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]

    slice_response = asyncio.run(_get_slice(dataset_id, "x", 2))

    _assert_png_response(slice_response)
    assert slice_response.headers["x-slice-axis"] == "x"
    assert slice_response.headers["x-slice-index"] == "2"


def test_segmentation_uses_matching_npy_override_for_tiff_dataset(
    _upload_storage_root,
) -> None:
    tiff_response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [
                (
                    "stack.tif",
                    _tiff_bytes(np.zeros((2, 3, 4), dtype=np.uint16)),
                    "image/tiff",
                )
            ],
        )
    )
    dataset_id = tiff_response.json()["dataset_id"]
    override = np.ones((2, 3, 4), dtype=np.float32)
    override_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [("override.npy", _npy_bytes(override), "application/octet-stream")],
            dataset_id=dataset_id,
            expected_dimensions={"x": 4, "y": 3, "z": 2},
        )
    )
    assert override_response.json()["dataset_id"] == dataset_id
    transport = httpx.ASGITransport(app=app)

    async def post_segmentation() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                f"/v1/datasets/{dataset_id}/segmentation",
                json={"threshold": 0.5},
            )

    response = asyncio.run(post_segmentation())

    assert response.status_code == 200
    payload = response.json()
    assert payload["foreground_voxel_count"] == override.size
    assert payload["background_voxel_count"] == 0
    np.testing.assert_array_equal(
        np.load(_upload_storage_root / dataset_id / "segmentation.npy"),
        np.ones_like(override, dtype=bool),
    )


def test_slice_returns_404_for_missing_dataset() -> None:
    response = asyncio.run(_get_slice("missing-dataset", "z", 0))

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found."


def test_slice_returns_400_for_out_of_range_index() -> None:
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "volume.npy",
                    _npy_bytes(np.arange(24, dtype=np.float32).reshape((2, 3, 4))),
                    "application/octet-stream",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]

    response = asyncio.run(_get_slice(dataset_id, "z", 2))

    assert response.status_code == 400
    assert "out of range" in response.json()["detail"]


def test_segmentation_view_returns_404_until_generated() -> None:
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "volume.npy",
                    _npy_bytes(np.arange(24, dtype=np.float32).reshape((2, 3, 4))),
                    "application/octet-stream",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]

    response = asyncio.run(_get_slice(dataset_id, "z", 0, view="segmentation"))

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "segmentation view has not been generated for this dataset."
    )


def test_skeleton_slice_view_is_reserved_for_structure_page() -> None:
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "volume.npy",
                    _npy_bytes(np.arange(24, dtype=np.float32).reshape((2, 3, 4))),
                    "application/octet-stream",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]

    response = asyncio.run(_get_slice(dataset_id, "z", 0, view="skeleton"))

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "skeleton view is reserved for the structure-analysis page."
    )


def test_threshold_preview_returns_mask_png_and_full_volume_counts() -> None:
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "volume.npy",
                    _npy_bytes(np.arange(24, dtype=np.float32).reshape((2, 3, 4))),
                    "application/octet-stream",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]
    transport = httpx.ASGITransport(app=app)

    async def post_preview() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                f"/v1/datasets/{dataset_id}/threshold-preview",
                json={"threshold": 10.5, "axis": "z", "index": 1},
            )

    response = asyncio.run(post_preview())

    _assert_png_response(response)
    assert response.headers["x-foreground-voxel-count"] == "13"
    assert response.headers["x-background-voxel-count"] == "11"
    assert response.headers["x-slice-min-intensity"] == "12.0"
    assert response.headers["x-slice-max-intensity"] == "23.0"


def test_threshold_preview_returns_400_for_out_of_range_index() -> None:
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "volume.npy",
                    _npy_bytes(np.arange(24, dtype=np.float32).reshape((2, 3, 4))),
                    "application/octet-stream",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]
    transport = httpx.ASGITransport(app=app)

    async def post_preview() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                f"/v1/datasets/{dataset_id}/threshold-preview",
                json={"threshold": 10.5, "axis": "z", "index": 2},
            )

    response = asyncio.run(post_preview())

    assert response.status_code == 400
    assert "out of range" in response.json()["detail"]


def test_voxel_probe_returns_real_intensity_and_mask_value() -> None:
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "volume.npy",
                    _npy_bytes(np.arange(24, dtype=np.float32).reshape((2, 3, 4))),
                    "application/octet-stream",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]
    transport = httpx.ASGITransport(app=app)

    async def post_probe() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                f"/v1/datasets/{dataset_id}/voxel-probe",
                json={"threshold": 10.5, "x": 3, "y": 2, "z": 1},
            )

    response = asyncio.run(post_probe())

    assert response.status_code == 200
    assert response.json() == {
        "x": 3,
        "y": 2,
        "z": 1,
        "intensity": 23.0,
        "mask_value": 1,
    }


def test_voxel_probe_returns_400_for_out_of_range_coordinate() -> None:
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "volume.npy",
                    _npy_bytes(np.arange(24, dtype=np.float32).reshape((2, 3, 4))),
                    "application/octet-stream",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]
    transport = httpx.ASGITransport(app=app)

    async def post_probe() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                f"/v1/datasets/{dataset_id}/voxel-probe",
                json={"threshold": 10.5, "x": 4, "y": 2, "z": 1},
            )

    response = asyncio.run(post_probe())

    assert response.status_code == 400
    assert response.json()["detail"] == "Voxel coordinate is out of range."


def test_segmentation_save_writes_mask_preview_and_returns_counts(_upload_storage_root) -> None:
    volume = np.arange(24, dtype=np.float32).reshape((2, 3, 4))
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [("volume.npy", _npy_bytes(volume), "application/octet-stream")],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]
    transport = httpx.ASGITransport(app=app)

    async def post_segmentation() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                f"/v1/datasets/{dataset_id}/segmentation",
                json={"threshold": 10.5},
            )

    response = asyncio.run(post_segmentation())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "saved"
    assert payload["dataset_id"] == dataset_id
    assert payload["threshold"] == 10.5
    assert payload["foreground_voxel_count"] == 13
    assert payload["background_voxel_count"] == 11
    assert payload["mask_path"] == "segmentation.npy"
    assert payload["slice_preview_path"] == "segmentation_slice_preview.png"

    dataset_dir = _upload_storage_root / dataset_id
    mask_path = dataset_dir / "segmentation.npy"
    preview_path = dataset_dir / "segmentation_slice_preview.png"
    assert mask_path.is_file()
    assert preview_path.is_file()
    assert preview_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    np.testing.assert_array_equal(np.load(mask_path), volume > 10.5)


def test_segmentation_save_returns_404_for_missing_dataset() -> None:
    transport = httpx.ASGITransport(app=app)

    async def post_segmentation() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/v1/datasets/missing-dataset/segmentation",
                json={"threshold": 10.5},
            )

    response = asyncio.run(post_segmentation())

    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset not found."


def test_segmentation_slice_view_returns_png_after_save() -> None:
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "volume.npy",
                    _npy_bytes(np.arange(24, dtype=np.float32).reshape((2, 3, 4))),
                    "application/octet-stream",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]
    transport = httpx.ASGITransport(app=app)

    async def save_and_fetch_slice() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                f"/v1/datasets/{dataset_id}/segmentation",
                json={"threshold": 10.5},
            )
            return await client.get(
                f"/v1/datasets/{dataset_id}/slices/z/1",
                params={"view": "segmentation"},
            )

    response = asyncio.run(save_and_fetch_slice())

    _assert_png_response(response)
    assert response.headers["x-view"] == "segmentation"


def test_analysis_job_runs_tiff_to_segmentation_and_skeleton_pipeline(
    _upload_storage_root,
) -> None:
    volume = np.zeros((5, 7, 7), dtype=np.uint16)
    volume[:, 3, 1:6] = 100
    volume[:, 1:6, 3] = 100
    intake_response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [("stack.tif", _tiff_bytes(volume), "image/tiff")],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]
    transport = httpx.ASGITransport(app=app)

    async def post_job() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                f"/v1/datasets/{dataset_id}/analysis-jobs",
                json={"project_id": "Pending", "dataset_name": "stack.tif"},
            )

    response = asyncio.run(post_job())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    assert payload["project_id"] != "Pending"
    assert payload["progress"] == ["queued", "segmenting", "skeletonizing", "complete"]
    assert payload["scale_unit"] == "pixels/voxels"
    assert payload["segmentation"]["foreground_voxel_count"] > 0
    assert payload["segmentation"]["background_voxel_count"] > 0
    assert payload["segmentation"]["dimensions"] == {"x": 7, "y": 7, "z": 5}
    assert payload["skeletonization"]["connected_components"] >= 1
    assert payload["skeletonization"]["endpoints"] >= 0
    assert payload["skeletonization"]["branch_points"] >= 0
    assert payload["skeletonization"]["bounds"]["unit"] == "pixels/voxels"
    for relative_path in [
        "segmentation.npy",
        "segmentation_summary.json",
        "skeleton.npy",
        "skeleton_summary.json",
    ]:
        assert (_upload_storage_root / dataset_id / relative_path).is_file()


def test_analysis_job_failure_stops_before_skeletonization(_upload_storage_root) -> None:
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "uniform.npy",
                    _npy_bytes(np.ones((3, 4, 5), dtype=np.float32)),
                    "application/octet-stream",
                )
            ],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]
    transport = httpx.ASGITransport(app=app)

    async def post_job() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(f"/v1/datasets/{dataset_id}/analysis-jobs", json={})

    response = asyncio.run(post_job())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["segmentation"] is None
    assert payload["skeletonization"] is None
    assert "intensity contrast" in payload["error"]
    assert not (_upload_storage_root / dataset_id / "skeleton.npy").exists()


def test_analysis_artifacts_can_be_reopened_after_refresh() -> None:
    volume = np.zeros((4, 6, 6), dtype=np.float32)
    volume[:, 2:4, 2:4] = 1.0
    intake_response = asyncio.run(
        _post_intake(
            "npyVolume",
            [("volume.npy", _npy_bytes(volume), "application/octet-stream")],
        )
    )
    dataset_id = intake_response.json()["dataset_id"]
    transport = httpx.ASGITransport(app=app)

    async def run_flow() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(f"/v1/datasets/{dataset_id}/analysis-jobs", json={})
            latest = await client.get(f"/v1/datasets/{dataset_id}/analysis-jobs/latest")
            segmentation = await client.get(
                f"/v1/datasets/{dataset_id}/slices/z/1",
                params={"view": "segmentation"},
            )
            manifest = await client.get(f"/v1/datasets/{dataset_id}/artifacts")
            skeleton = await client.get(
                f"/v1/datasets/{dataset_id}/artifacts/skeleton"
            )
            skeleton_summary = await client.get(
                f"/v1/datasets/{dataset_id}/artifacts/skeleton_summary"
            )
            return latest, segmentation, manifest, skeleton, skeleton_summary

    (
        latest_response,
        segmentation_response,
        manifest_response,
        skeleton_response,
        skeleton_summary_response,
    ) = asyncio.run(run_flow())

    assert latest_response.status_code == 200
    assert latest_response.json()["status"] == "complete"
    _assert_png_response(segmentation_response)
    assert segmentation_response.headers["x-view"] == "segmentation"
    assert manifest_response.status_code == 200
    assert manifest_response.json()["artifacts"]["segmentation_mask"]["path"] == (
        "segmentation.npy"
    )
    assert manifest_response.json()["artifacts"]["skeleton"]["path"] == "skeleton.npy"
    assert skeleton_response.status_code == 200
    assert skeleton_response.headers["content-type"] == "application/octet-stream"
    assert skeleton_summary_response.status_code == 200
    assert skeleton_summary_response.json()["bounds"]["unit"] == "pixels/voxels"
