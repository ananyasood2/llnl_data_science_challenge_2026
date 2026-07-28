"""Dataset intake route tests."""

from __future__ import annotations

import asyncio
from io import BytesIO
from uuid import UUID

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
    origin: str | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    multipart_files = [
        ("files", (file_name, contents, content_type))
        for file_name, contents, content_type in files
    ]

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/v1/datasets/intake",
            data={"slot": slot},
            files=multipart_files,
            headers={"Origin": origin} if origin else None,
        )


def _npy_bytes() -> bytes:
    buffer = BytesIO()
    np.save(buffer, np.arange(24, dtype=np.float32).reshape((2, 3, 4)))
    return buffer.getvalue()


def _tiff_bytes(array: np.ndarray, *, resolution: tuple[int, int] | None = None) -> bytes:
    buffer = BytesIO()
    options = {}
    if resolution is not None:
        options = {"resolution": resolution, "resolutionunit": "INCH"}

    tifffile.imwrite(buffer, array, **options)
    return buffer.getvalue()


def _assert_saved_dataset(payload: dict, upload_storage_root, file_names: list[str]) -> None:
    dataset_id = payload["dataset_id"]
    UUID(dataset_id)

    dataset_dir = upload_storage_root / dataset_id
    assert dataset_dir.is_dir()
    assert sorted(path.name for path in dataset_dir.iterdir()) == sorted(file_names)


def test_dataset_intake_extracts_npy_metadata(_upload_storage_root) -> None:
    response = asyncio.run(
        _post_intake(
            "npyVolume",
            [("volume.npy", _npy_bytes(), "application/octet-stream")],
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    _assert_saved_dataset(payload, _upload_storage_root, ["volume.npy"])
    assert payload["slot"] == "npyVolume"
    assert payload["file_names"] == ["volume.npy"]
    assert payload["file_type"] == "npy"
    assert payload["dimensions"] == {"x": 4, "y": 3, "z": 2}
    assert payload["intensity_range"] == {"min": 0.0, "max": 23.0}
    assert payload["embedded_metadata"] == {
        "dtype": "float32",
        "shape": [2, 3, 4],
    }
    assert payload["voxel_size_micron"] is None
    assert payload["warnings"]
    assert payload["errors"] == []
    assert payload["demo_mode"] is True


def test_dataset_intake_rejects_wrong_file_type_for_slot() -> None:
    response = asyncio.run(
        _post_intake(
            "npyVolume",
            [("volume.txt", b"not numpy", "text/plain")],
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["dataset_id"] is None
    assert payload["slot"] == "npyVolume"
    assert payload["dimensions"] is None
    assert payload["intensity_range"] is None
    assert payload["errors"] == [
        "volume.txt is not valid for npyVolume. Expected one of: .npy."
    ]


def test_dataset_intake_extracts_single_multipage_tiff_metadata(_upload_storage_root) -> None:
    stack = np.arange(24, dtype=np.uint16).reshape((2, 3, 4))
    response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [("stack.tif", _tiff_bytes(stack, resolution=(1000, 1000)), "image/tiff")],
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    _assert_saved_dataset(payload, _upload_storage_root, ["stack.tif"])
    assert payload["slot"] == "ctTiffStack"
    assert payload["file_names"] == ["stack.tif"]
    assert payload["file_type"] == "tiff"
    assert payload["dimensions"] == {"x": 4, "y": 3, "z": 2}
    assert payload["intensity_range"] == {"min": 0.0, "max": 23.0}
    assert payload["embedded_metadata"]["XResolution"] == [1000, 1]
    assert payload["embedded_metadata"]["YResolution"] == [1000, 1]
    assert payload["voxel_size_micron"] == 25.4
    assert payload["warnings"] == []
    assert payload["errors"] == []
    assert payload["demo_mode"] is False


def test_dataset_intake_allows_127_frontend_origin_for_tiff_upload(
    _upload_storage_root,
) -> None:
    stack = np.arange(24, dtype=np.uint16).reshape((2, 3, 4))
    response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [("stack.tif", _tiff_bytes(stack), "image/tiff")],
            origin="http://127.0.0.1:3000",
        )
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert response.json()["valid"] is True


def test_dataset_intake_extracts_multi_file_tiff_stack_metadata(_upload_storage_root) -> None:
    first_slice = np.array([[1, 2], [3, 4]], dtype=np.uint16)
    second_slice = np.array([[5, 6], [7, 8]], dtype=np.uint16)
    response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [
                ("slice-001.tif", _tiff_bytes(first_slice), "image/tiff"),
                ("slice-002.tif", _tiff_bytes(second_slice), "image/tiff"),
            ],
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    _assert_saved_dataset(payload, _upload_storage_root, ["slice-001.tif", "slice-002.tif"])
    assert payload["dimensions"] == {"x": 2, "y": 2, "z": 2}
    assert payload["intensity_range"] == {"min": 1.0, "max": 8.0}
    assert payload["voxel_size_micron"] is None
    assert payload["warnings"] == [
        "Voxel size could not be read from TIFF metadata; enter voxel_size_micron manually."
    ]
    assert payload["errors"] == []
    assert payload["demo_mode"] is False


def test_dataset_intake_naturally_sorts_multi_file_tiff_stack(_upload_storage_root) -> None:
    response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [
                ("slice_10.tif", _tiff_bytes(np.full((2, 2), 10, dtype=np.uint16)), "image/tiff"),
                ("slice_2.tif", _tiff_bytes(np.full((2, 2), 2, dtype=np.uint16)), "image/tiff"),
                ("slice_1.tif", _tiff_bytes(np.full((2, 2), 1, dtype=np.uint16)), "image/tiff"),
            ],
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    _assert_saved_dataset(
        payload,
        _upload_storage_root,
        ["slice_1.tif", "slice_2.tif", "slice_10.tif"],
    )
    assert payload["file_names"] == ["slice_1.tif", "slice_2.tif", "slice_10.tif"]
    assert payload["dimensions"] == {"x": 2, "y": 2, "z": 3}
    assert payload["intensity_range"] == {"min": 1.0, "max": 10.0}


def test_dataset_intake_returns_error_for_corrupt_tiff() -> None:
    response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [("broken.tif", b"not a real tiff", "image/tiff")],
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["dataset_id"] is None
    assert payload["slot"] == "ctTiffStack"
    assert payload["dimensions"] is None
    assert payload["intensity_range"] is None
    assert payload["warnings"] == []
    assert payload["errors"][0].startswith("Unable to read TIFF stack:")
