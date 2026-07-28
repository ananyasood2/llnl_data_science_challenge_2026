"""Dataset intake route tests."""

from __future__ import annotations

import asyncio
import os
import struct
from io import BytesIO
from pathlib import Path
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
    expected_dimensions: dict[str, int] | None = None,
    dataset_id: str | None = None,
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
            headers={"Origin": origin} if origin else None,
        )


def _npy_bytes(array: np.ndarray | None = None) -> bytes:
    buffer = BytesIO()
    np.save(
        buffer,
        array
        if array is not None
        else np.arange(24, dtype=np.float32).reshape((2, 3, 4)),
    )
    return buffer.getvalue()


def _tiff_bytes(array: np.ndarray, *, resolution: tuple[int, int] | None = None) -> bytes:
    buffer = BytesIO()
    options = {}
    if resolution is not None:
        options = {"resolution": resolution, "resolutionunit": "INCH"}

    tifffile.imwrite(buffer, array, **options)
    return buffer.getvalue()


def _ascii_stl_bytes() -> bytes:
    return b"""solid tetra
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
facet normal 0 -1 0
  outer loop
    vertex 0 0 0
    vertex 0 0 1
    vertex 1 0 0
  endloop
endfacet
facet normal 1 1 1
  outer loop
    vertex 1 0 0
    vertex 0 0 1
    vertex 0 1 0
  endloop
endfacet
facet normal -1 0 0
  outer loop
    vertex 0 0 0
    vertex 0 1 0
    vertex 0 0 1
  endloop
endfacet
endsolid tetra
"""


def _binary_stl_bytes() -> bytes:
    triangles = [
        ((0.0, 0.0, 1.0), ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))),
        ((0.0, -1.0, 0.0), ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0))),
        ((1.0, 1.0, 1.0), ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))),
        ((-1.0, 0.0, 0.0), ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))),
    ]
    payload = bytearray(b"binary tetra".ljust(80, b"\x00"))
    payload.extend(struct.pack("<I", len(triangles)))
    for normal, vertices in triangles:
        values = [*normal, *vertices[0], *vertices[1], *vertices[2]]
        payload.extend(struct.pack("<12fH", *values, 0))
    return bytes(payload)


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
    _assert_saved_dataset(
        payload,
        _upload_storage_root,
        ["normalized_volume.npy", "stack.tif"],
    )
    assert payload["slot"] == "ctTiffStack"
    assert payload["file_names"] == ["stack.tif"]
    assert payload["generated_file_names"] == ["normalized_volume.npy"]
    assert payload["file_type"] == "tiff"
    assert payload["dimensions"] == {"x": 4, "y": 3, "z": 2}
    assert payload["intensity_range"] == {"min": 0.0, "max": 23.0}
    assert payload["embedded_metadata"]["XResolution"] == [1000, 1]
    assert payload["embedded_metadata"]["YResolution"] == [1000, 1]
    assert payload["voxel_size_micron"] == 25.4
    assert payload["warnings"] == []
    assert payload["errors"] == []
    assert payload["demo_mode"] is False

    generated_volume = np.load(
        _upload_storage_root / payload["dataset_id"] / "normalized_volume.npy",
        allow_pickle=False,
    )
    assert generated_volume.dtype == np.float32
    assert generated_volume.shape == stack.shape
    assert float(generated_volume.min()) == 0.0
    assert float(generated_volume.max()) == 1.0


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
    _assert_saved_dataset(
        payload,
        _upload_storage_root,
        ["normalized_volume.npy", "slice-001.tif", "slice-002.tif"],
    )
    assert payload["dimensions"] == {"x": 2, "y": 2, "z": 2}
    assert payload["intensity_range"] == {"min": 1.0, "max": 8.0}
    assert payload["voxel_size_micron"] is None
    assert payload["warnings"] == [
        "Voxel size could not be read from TIFF metadata; measurements remain in pixels/voxels until a verified voxel_size_micron is provided."
    ]
    assert payload["errors"] == []
    assert payload["demo_mode"] is False

    generated_volume = np.load(
        _upload_storage_root / payload["dataset_id"] / "normalized_volume.npy",
        allow_pickle=False,
    )
    np.testing.assert_allclose(
        generated_volume,
        np.array([[[0.0, 1 / 7], [2 / 7, 3 / 7]], [[4 / 7, 5 / 7], [6 / 7, 1.0]]], dtype=np.float32),
    )


def test_dataset_intake_rejects_npy_override_with_mismatched_tiff_dimensions() -> None:
    response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "other-dataset.npy",
                    _npy_bytes(np.arange(60, dtype=np.float32).reshape((3, 4, 5))),
                    "application/octet-stream",
                )
            ],
            expected_dimensions={"x": 4, "y": 3, "z": 2},
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["dataset_id"] is None
    assert payload["dimensions"] == {"x": 5, "y": 4, "z": 3}
    assert payload["errors"] == [
        (
            "Uploaded .npy override dimensions must match the validated TIFF stack "
            "dimensions; expected 4 x 3 x 2, got 5 x 4 x 3."
        )
    ]


def test_dataset_intake_accepts_npy_override_with_matching_tiff_dimensions(
    _upload_storage_root,
) -> None:
    response = asyncio.run(
        _post_intake(
            "npyVolume",
            [
                (
                    "override.npy",
                    _npy_bytes(np.arange(24, dtype=np.float32).reshape((2, 3, 4))),
                    "application/octet-stream",
                )
            ],
            expected_dimensions={"x": 4, "y": 3, "z": 2},
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    _assert_saved_dataset(payload, _upload_storage_root, ["override.npy"])


def test_dataset_intake_stores_npy_override_with_existing_tiff_dataset(
    _upload_storage_root,
) -> None:
    tiff_response = asyncio.run(
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
    dataset_id = tiff_response.json()["dataset_id"]
    override = (np.arange(24, dtype=np.float32).reshape((2, 3, 4)) + 100.0)

    response = asyncio.run(
        _post_intake(
            "npyVolume",
            [("from-same-stack.npy", _npy_bytes(override), "application/octet-stream")],
            expected_dimensions={"x": 4, "y": 3, "z": 2},
            dataset_id=dataset_id,
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["dataset_id"] == dataset_id
    dataset_dir = _upload_storage_root / dataset_id
    assert (dataset_dir / "normalized_volume.npy").is_file()
    assert (dataset_dir / "override_volume.npy").is_file()
    np.testing.assert_array_equal(
        np.load(dataset_dir / "override_volume.npy", allow_pickle=False),
        override,
    )


def test_dataset_intake_extracts_ascii_stl_metadata(_upload_storage_root) -> None:
    response = asyncio.run(
        _post_intake(
            "stlCad",
            [("reference.stl", _ascii_stl_bytes(), "model/stl")],
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    _assert_saved_dataset(payload, _upload_storage_root, ["reference.stl"])
    assert payload["file_type"] == "stl"
    assert payload["geometry_metadata"] == {
        "format": "stl-ascii",
        "triangle_count": 4,
        "vertex_count": 4,
        "dimensions": {"x": 1.0, "y": 1.0, "z": 1.0},
        "bounds": {"x": [0.0, 1.0], "y": [0.0, 1.0], "z": [0.0, 1.0]},
    }
    assert payload["warnings"] == [
        "STL units are unspecified; use project voxel-size and design-context fields for physical scale."
    ]
    assert payload["errors"] == []


def test_dataset_intake_extracts_binary_stl_metadata(_upload_storage_root) -> None:
    response = asyncio.run(
        _post_intake(
            "stlCad",
            [("reference.stl", _binary_stl_bytes(), "application/octet-stream")],
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["geometry_metadata"]["format"] == "stl-binary"
    assert payload["geometry_metadata"]["triangle_count"] == 4
    assert payload["geometry_metadata"]["vertex_count"] == 4
    assert payload["geometry_metadata"]["dimensions"] == {"x": 1.0, "y": 1.0, "z": 1.0}


def test_dataset_intake_stores_stl_with_existing_tiff_dataset(_upload_storage_root) -> None:
    tiff_response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [("stack.tif", _tiff_bytes(np.zeros((2, 3, 4), dtype=np.uint16)), "image/tiff")],
        )
    )
    dataset_id = tiff_response.json()["dataset_id"]

    response = asyncio.run(
        _post_intake(
            "stlCad",
            [("design-reference.stl", _ascii_stl_bytes(), "model/stl")],
            dataset_id=dataset_id,
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["dataset_id"] == dataset_id
    assert (_upload_storage_root / dataset_id / "design-reference.stl").is_file()


@pytest.mark.parametrize(
    ("contents", "expected_error"),
    [
        (b"", "STL file is empty."),
        (
            b"solid broken\nfacet normal 0 0 1\nouter loop\nvertex nan 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid\n",
            "STL geometry contains non-finite coordinates",
        ),
        (
            b"solid flat\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 2 0 0\nendloop\nendfacet\nendsolid\n",
            "STL geometry contains a degenerate triangle",
        ),
        (b"not an stl", "ASCII STL is malformed: missing solid header."),
    ],
)
def test_dataset_intake_rejects_invalid_stl(contents: bytes, expected_error: str) -> None:
    response = asyncio.run(
        _post_intake(
            "stlCad",
            [("bad.stl", contents, "model/stl")],
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["dataset_id"] is None
    assert payload["geometry_metadata"] is None
    assert payload["warnings"] == []
    assert payload["errors"][0].startswith(expected_error)


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
        ["normalized_volume.npy", "slice_1.tif", "slice_2.tif", "slice_10.tif"],
    )
    assert payload["file_names"] == ["slice_1.tif", "slice_2.tif", "slice_10.tif"]
    assert payload["dimensions"] == {"x": 2, "y": 2, "z": 3}
    assert payload["intensity_range"] == {"min": 1.0, "max": 10.0}

    generated_volume = np.load(
        _upload_storage_root / payload["dataset_id"] / "normalized_volume.npy",
        allow_pickle=False,
    )
    np.testing.assert_allclose(generated_volume[:, 0, 0], [0.0, 1.0 / 9.0, 1.0])


def test_missing_struts_tiff_reaches_ready_state_without_npy_upload(
    _upload_storage_root,
) -> None:
    if os.environ.get("RUN_SLOW_INTAKE_TESTS") != "1":
        pytest.skip("Set RUN_SLOW_INTAKE_TESTS=1 to run the 992 MB TIFF intake test.")

    tiff_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "missing_struts"
        / "tif_stacks"
        / "210127_Brian_Tran_strut_lattices_0point5dash1 1 Slices.tif"
    )
    if not tiff_path.is_file():
        pytest.skip("missing_struts TIFF is not present in this checkout.")

    response = asyncio.run(
        _post_intake(
            "ctTiffStack",
            [(tiff_path.name, tiff_path.read_bytes(), "image/tiff")],
        )
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["slot"] == "ctTiffStack"
    assert payload["dimensions"]["x"] is not None
    assert payload["dimensions"]["y"] is not None
    assert payload["dimensions"]["z"] is not None
    assert payload["generated_file_names"] == ["normalized_volume.npy"]
    assert payload["voxel_size_micron"] is None
    assert payload["warnings"] == [
        "Voxel size could not be read from TIFF metadata; measurements remain in pixels/voxels until a verified voxel_size_micron is provided."
    ]
    assert (_upload_storage_root / payload["dataset_id"] / "normalized_volume.npy").is_file()


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
