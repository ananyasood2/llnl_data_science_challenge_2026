"""Dataset intake endpoints."""

from __future__ import annotations

import json
import re
import struct
import uuid
import zlib
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, NamedTuple

import numpy as np
import tifffile
from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.schemas.datasets import (
    DatasetDimensions,
    DatasetIntakeResponse,
    DatasetSlot,
    GeometryBounds,
    GeometryMetadata,
    IntensityRange,
)

router = APIRouter(prefix="/v1/datasets", tags=["datasets"])

ALLOWED_EXTENSIONS: dict[DatasetSlot, set[str]] = {
    "ctTiffStack": {".tif", ".tiff"},
    "npyVolume": {".npy"},
    "stlCad": {".stl", ".step", ".stp"},
    "graphJson": {".json", ".graphml"},
}


class UploadedDatasetFile(NamedTuple):
    file_name: str
    contents: bytes


SliceAxis = Literal["x", "y", "z"]
SliceView = Literal["original", "segmentation", "skeleton"]


class ThresholdPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float
    axis: SliceAxis
    index: int


class SegmentationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float


class SegmentationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    dataset_id: str
    threshold: float
    foreground_voxel_count: int
    background_voxel_count: int
    mask_path: str
    slice_preview_path: str
    demo_mode: bool


class VoxelProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float
    x: int
    y: int
    z: int


class VoxelProbeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int
    z: int
    intensity: float
    mask_value: int


@router.post("/intake", response_model=DatasetIntakeResponse)
async def intake_dataset(
    slot: DatasetSlot = Form(...),
    files: list[UploadFile] = File(...),
    dataset_id: str | None = Form(None),
    expected_x: int | None = Form(None),
    expected_y: int | None = Form(None),
    expected_z: int | None = Form(None),
) -> DatasetIntakeResponse:
    """Validate uploaded dataset files and return compact intake metadata."""
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required.")

    uploaded_files = [
        UploadedDatasetFile(upload.filename or "unnamed", await upload.read())
        for upload in files
    ]
    file_names = [uploaded_file.file_name for uploaded_file in uploaded_files]
    errors = _validate_extensions(slot, file_names)

    try:
        if errors:
            return DatasetIntakeResponse(
                valid=False,
                slot=slot,
                file_names=file_names,
                file_type=None,
                warnings=[],
                errors=errors,
                demo_mode=get_settings().demo_mode,
            )

        generated_files: list[UploadedDatasetFile] = []

        if slot == "npyVolume":
            response = _intake_npy(
                slot,
                uploaded_files[0],
                file_names,
                expected_dimensions=_expected_dimensions(expected_x, expected_y, expected_z),
            )
        elif slot == "graphJson":
            response = _intake_graph(slot, uploaded_files[0], file_names)
        elif slot == "ctTiffStack":
            response = _intake_tiff_stack(slot, uploaded_files)
            if response.valid:
                generated_files = [
                    UploadedDatasetFile(
                        "normalized_volume.npy",
                        _npy_bytes_from_array(
                            _normalize_volume_for_storage(
                                _load_tiff_stack_from_uploads(uploaded_files)
                            )
                        ),
                    )
                ]
                response = response.model_copy(
                    update={
                        "generated_file_names": [
                            file.file_name for file in generated_files
                        ]
                    }
                )
        else:
            response = _intake_design_file(slot, uploaded_files[0], file_names)

        if not response.valid:
            return response

        persisted_dataset_id = _persist_intake_assets(
            slot,
            uploaded_files,
            generated_files,
            existing_dataset_id=dataset_id,
        )
        return response.model_copy(update={"dataset_id": persisted_dataset_id})
    finally:
        for upload in files:
            await upload.close()


@router.get("/{dataset_id}/slices/{axis}/{index}")
async def get_dataset_slice(
    dataset_id: str,
    axis: SliceAxis,
    index: int,
    view: SliceView = Query("original"),
) -> Response:
    """Return a normalized PNG slice for a persisted dataset volume."""
    if view == "skeleton":
        raise HTTPException(
            status_code=404,
            detail=f"{view} view has not been generated for this dataset.",
        )

    storage_root = get_settings().upload_storage_root
    dataset_dir = storage_root / dataset_id

    if not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="Dataset not found.")

    if view == "segmentation":
        segmentation_path = dataset_dir / "segmentation.npy"
        if not segmentation_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="segmentation view has not been generated for this dataset.",
            )
        volume = _as_zyx_volume(np.load(segmentation_path, allow_pickle=False))
    else:
        volume = _load_cached_original_volume(str(storage_root), dataset_id)
    max_index = _axis_size(volume, axis) - 1

    if index < 0 or index > max_index:
        raise HTTPException(
            status_code=400,
            detail=f"Slice index {index} is out of range for axis {axis}; expected 0..{max_index}.",
        )

    image = _extract_slice(volume, axis, index)
    png = _encode_grayscale_png(_normalize_to_uint8(image))

    return Response(
        content=png,
        media_type="image/png",
        headers={
            "X-Slice-Axis": axis,
            "X-Slice-Index": str(index),
            "X-View": view,
        },
    )


@router.post("/{dataset_id}/segmentation", response_model=SegmentationResponse)
async def save_segmentation(
    dataset_id: str,
    request: SegmentationRequest,
) -> SegmentationResponse:
    """Persist a deterministic threshold segmentation result."""
    volume = _get_existing_cached_volume(dataset_id)
    dataset_dir = get_settings().upload_storage_root / dataset_id
    mask = volume > request.threshold
    foreground_voxel_count = int(np.count_nonzero(mask))
    background_voxel_count = int(mask.size - foreground_voxel_count)
    mask_path = dataset_dir / "segmentation.npy"
    slice_preview_path = dataset_dir / "segmentation_slice_preview.png"
    middle_z = volume.shape[0] // 2
    preview = _extract_slice(mask, "z", middle_z).astype(np.uint8) * 255

    # This commits the exact user-selected threshold with mask = volume > threshold.
    # It is deliberately simpler than segmentation_agent.toml's autonomous,
    # multi-iteration agent workflow.
    np.save(mask_path, mask)
    slice_preview_path.write_bytes(_encode_grayscale_png(preview))

    return SegmentationResponse(
        status="saved",
        dataset_id=dataset_id,
        threshold=request.threshold,
        foreground_voxel_count=foreground_voxel_count,
        background_voxel_count=background_voxel_count,
        mask_path="segmentation.npy",
        slice_preview_path="segmentation_slice_preview.png",
        demo_mode=get_settings().demo_mode,
    )


@router.post("/{dataset_id}/threshold-preview")
async def create_threshold_preview(
    dataset_id: str,
    request: ThresholdPreviewRequest,
) -> Response:
    """Return a cheap deterministic mask preview: mask = volume > threshold."""
    volume = _get_existing_cached_volume(dataset_id)
    max_index = _axis_size(volume, request.axis) - 1

    if request.index < 0 or request.index > max_index:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Slice index {request.index} is out of range for axis "
                f"{request.axis}; expected 0..{max_index}."
            ),
        )

    mask = volume > request.threshold
    foreground_voxel_count = int(np.count_nonzero(mask))
    background_voxel_count = int(mask.size - foreground_voxel_count)
    mask_slice = _extract_slice(mask, request.axis, request.index).astype(np.uint8) * 255
    source_slice = _extract_slice(volume, request.axis, request.index)
    png = _encode_grayscale_png(mask_slice)
    slice_min, slice_max = _finite_min_max(source_slice)

    return Response(
        content=png,
        media_type="image/png",
        headers={
            "X-Foreground-Voxel-Count": str(foreground_voxel_count),
            "X-Background-Voxel-Count": str(background_voxel_count),
            "X-Slice-Min-Intensity": str(slice_min),
            "X-Slice-Max-Intensity": str(slice_max),
            "X-Slice-Width-Px": str(mask_slice.shape[1]),
            "X-Slice-Height-Px": str(mask_slice.shape[0]),
            "X-Threshold": str(request.threshold),
        },
    )


@router.post("/{dataset_id}/voxel-probe", response_model=VoxelProbeResponse)
async def probe_dataset_voxel(
    dataset_id: str,
    request: VoxelProbeRequest,
) -> VoxelProbeResponse:
    """Return real voxel intensity and preview mask value for one coordinate."""
    volume = _get_existing_cached_volume(dataset_id)

    if (
        request.x < 0
        or request.y < 0
        or request.z < 0
        or request.x >= volume.shape[2]
        or request.y >= volume.shape[1]
        or request.z >= volume.shape[0]
    ):
        raise HTTPException(status_code=400, detail="Voxel coordinate is out of range.")

    intensity = float(volume[request.z, request.y, request.x])

    return VoxelProbeResponse(
        x=request.x,
        y=request.y,
        z=request.z,
        intensity=intensity,
        mask_value=1 if intensity > request.threshold else 0,
    )


def _validate_extensions(slot: DatasetSlot, file_names: list[str]) -> list[str]:
    allowed = ALLOWED_EXTENSIONS[slot]
    errors: list[str] = []

    for file_name in file_names:
        suffix = Path(file_name).suffix.lower()
        if suffix not in allowed:
            allowed_list = ", ".join(sorted(allowed))
            errors.append(
                f"{file_name} is not valid for {slot}. Expected one of: {allowed_list}."
            )

    return errors


def _intake_npy(
    slot: DatasetSlot,
    upload: UploadedDatasetFile,
    file_names: list[str],
    *,
    expected_dimensions: DatasetDimensions | None = None,
) -> DatasetIntakeResponse:
    try:
        array = _load_npy_volume_from_bytes(upload.contents)
    except Exception as exc:
        return DatasetIntakeResponse(
            valid=False,
            slot=slot,
            file_names=file_names,
            file_type="npy",
            warnings=[],
            errors=[f"Unable to read .npy volume: {exc}"],
            demo_mode=get_settings().demo_mode,
        )

    if array.ndim < 2 or array.ndim > 3:
        return DatasetIntakeResponse(
            valid=False,
            slot=slot,
            file_names=file_names,
            file_type="npy",
            dimensions=None,
            intensity_range=None,
            embedded_metadata={"dtype": str(array.dtype), "shape": list(array.shape)},
            voxel_size_micron=None,
            warnings=[],
            errors=["Expected a 2D slice or 3D CT volume in .npy format."],
            demo_mode=get_settings().demo_mode,
        )

    dimensions = _dimensions_from_shape(array.shape)

    if expected_dimensions is not None and dimensions != expected_dimensions:
        expected = format_dimensions(expected_dimensions)
        actual = format_dimensions(dimensions)
        return DatasetIntakeResponse(
            valid=False,
            slot=slot,
            file_names=file_names,
            file_type="npy",
            dimensions=dimensions,
            intensity_range=None,
            embedded_metadata={"dtype": str(array.dtype), "shape": list(array.shape)},
            voxel_size_micron=None,
            warnings=[],
            errors=[
                (
                    "Uploaded .npy override dimensions must match the validated "
                    f"TIFF stack dimensions; expected {expected}, got {actual}."
                )
            ],
            demo_mode=get_settings().demo_mode,
        )

    intensity_range = IntensityRange(min=float(np.min(array)), max=float(np.max(array)))

    return DatasetIntakeResponse(
        valid=True,
        slot=slot,
        file_names=file_names,
        file_type="npy",
        dimensions=dimensions,
        intensity_range=intensity_range,
        embedded_metadata={"dtype": str(array.dtype), "shape": list(array.shape)},
        voxel_size_micron=None,
        warnings=[
            "Voxel size could not be read from .npy metadata; enter voxel_size_micron manually."
        ],
        errors=[],
        demo_mode=get_settings().demo_mode,
    )


def _intake_graph(
    slot: DatasetSlot,
    upload: UploadedDatasetFile,
    file_names: list[str],
) -> DatasetIntakeResponse:
    suffix = Path(upload.file_name).suffix.lower()

    if suffix != ".json":
        return DatasetIntakeResponse(
            valid=True,
            slot=slot,
            file_names=file_names,
            file_type=suffix.lstrip("."),
            dimensions=None,
            intensity_range=None,
            embedded_metadata=None,
            voxel_size_micron=None,
            warnings=[
                "GraphML parsing is not implemented yet; file type was validated only.",
                "Voxel size could not be read from graph metadata.",
            ],
            errors=[],
            demo_mode=True,
        )

    try:
        graph_data = json.loads(upload.contents.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return DatasetIntakeResponse(
            valid=False,
            slot=slot,
            file_names=file_names,
            file_type="json",
            warnings=[],
            errors=[f"Unable to parse graph JSON: {exc}"],
            demo_mode=get_settings().demo_mode,
        )

    embedded_metadata = _extract_json_metadata(graph_data)
    voxel_size_micron = _find_numeric_metadata(graph_data, "voxel_size_micron")
    warnings = []

    if voxel_size_micron is None:
        warnings.append("Voxel size could not be read from graph metadata.")

    return DatasetIntakeResponse(
        valid=True,
        slot=slot,
        file_names=file_names,
        file_type="json",
        dimensions=None,
        intensity_range=None,
        embedded_metadata=embedded_metadata,
        voxel_size_micron=voxel_size_micron,
        warnings=warnings,
        errors=[],
        demo_mode=get_settings().demo_mode,
    )


def _intake_tiff_stack(
    slot: DatasetSlot,
    uploads: list[UploadedDatasetFile],
) -> DatasetIntakeResponse:
    sorted_uploads = sorted(uploads, key=lambda upload: _natural_sort_key(upload.file_name))
    sorted_file_names = [upload.file_name for upload in sorted_uploads]
    stack_depth = 0
    x_dimension: int | None = None
    y_dimension: int | None = None
    intensity_min: float | None = None
    intensity_max: float | None = None
    embedded_metadata: dict[str, Any] = {}
    voxel_size_micron: float | None = None

    for index, upload in enumerate(sorted_uploads):
        try:
            with tifffile.TiffFile(BytesIO(upload.contents)) as tiff:
                array = _load_tiff_volume_from_bytes(upload.contents)
                if index == 0:
                    embedded_metadata = _extract_tiff_metadata(tiff)
                    voxel_size_micron = _voxel_size_micron_from_tiff_metadata(
                        embedded_metadata
                    )
        except Exception as exc:
            return DatasetIntakeResponse(
                valid=False,
                slot=slot,
                file_names=sorted_file_names,
                file_type="tiff",
                dimensions=None,
                intensity_range=None,
                embedded_metadata=None,
                voxel_size_micron=None,
                warnings=[],
                errors=[f"Unable to read TIFF stack: {exc}"],
                demo_mode=get_settings().demo_mode,
            )

        if array.ndim == 2:
            current_z, current_y, current_x = 1, array.shape[0], array.shape[1]
        elif array.ndim == 3:
            current_z, current_y, current_x = (
                array.shape[0],
                array.shape[1],
                array.shape[2],
            )
        else:
            return DatasetIntakeResponse(
                valid=False,
                slot=slot,
                file_names=sorted_file_names,
                file_type="tiff",
                dimensions=None,
                intensity_range=None,
                embedded_metadata=embedded_metadata or None,
                voxel_size_micron=voxel_size_micron,
                warnings=[],
                errors=[
                    "Expected a 2D TIFF slice, multi-page TIFF stack, or 3D TIFF volume."
                ],
                demo_mode=get_settings().demo_mode,
            )

        if x_dimension is None or y_dimension is None:
            x_dimension = current_x
            y_dimension = current_y
        elif x_dimension != current_x or y_dimension != current_y:
            return DatasetIntakeResponse(
                valid=False,
                slot=slot,
                file_names=sorted_file_names,
                file_type="tiff",
                dimensions=None,
                intensity_range=None,
                embedded_metadata=embedded_metadata or None,
                voxel_size_micron=voxel_size_micron,
                warnings=[],
                errors=["All TIFF slices in a CT stack must share the same x/y dimensions."],
                demo_mode=get_settings().demo_mode,
            )

        stack_depth += current_z
        current_min = float(np.min(array))
        current_max = float(np.max(array))
        intensity_min = current_min if intensity_min is None else min(intensity_min, current_min)
        intensity_max = current_max if intensity_max is None else max(intensity_max, current_max)

    warnings = []

    if voxel_size_micron is None:
        warnings.append(
            "Voxel size could not be read from TIFF metadata; measurements remain in pixels/voxels until a verified voxel_size_micron is provided."
        )

    return DatasetIntakeResponse(
        valid=True,
        slot=slot,
        file_names=sorted_file_names,
        file_type="tiff",
        dimensions=DatasetDimensions(x=x_dimension, y=y_dimension, z=stack_depth),
        intensity_range=IntensityRange(min=intensity_min or 0.0, max=intensity_max or 0.0),
        embedded_metadata=embedded_metadata or None,
        voxel_size_micron=voxel_size_micron,
        warnings=warnings,
        errors=[],
        demo_mode=False,
    )


def _intake_design_file(
    slot: DatasetSlot,
    upload: UploadedDatasetFile,
    file_names: list[str],
) -> DatasetIntakeResponse:
    suffix = Path(file_names[0]).suffix.lower()
    if suffix != ".stl":
        return DatasetIntakeResponse(
            valid=True,
            slot=slot,
            file_names=file_names,
            file_type=suffix.lstrip("."),
            dimensions=None,
            intensity_range=None,
            geometry_metadata=None,
            embedded_metadata=None,
            voxel_size_micron=None,
            warnings=[
                "STEP/STP geometry parsing is not implemented yet; file type was validated only."
            ],
            errors=[],
            demo_mode=True,
        )

    try:
        geometry_metadata = _parse_stl_metadata(upload.contents)
    except ValueError as exc:
        return DatasetIntakeResponse(
            valid=False,
            slot=slot,
            file_names=file_names,
            file_type="stl",
            dimensions=None,
            intensity_range=None,
            geometry_metadata=None,
            embedded_metadata=None,
            voxel_size_micron=None,
            warnings=[],
            errors=[str(exc)],
            demo_mode=get_settings().demo_mode,
        )

    return DatasetIntakeResponse(
        valid=True,
        slot=slot,
        file_names=file_names,
        file_type="stl",
        dimensions=None,
        intensity_range=None,
        geometry_metadata=geometry_metadata,
        embedded_metadata=None,
        voxel_size_micron=None,
        warnings=[
            "STL units are unspecified; use project voxel-size and design-context fields for physical scale."
        ],
        errors=[],
        demo_mode=get_settings().demo_mode,
    )


def _parse_stl_metadata(contents: bytes) -> GeometryMetadata:
    if not contents:
        raise ValueError("STL file is empty.")

    if _looks_like_binary_stl(contents):
        return _parse_binary_stl_metadata(contents)

    try:
        return _parse_ascii_stl_metadata(contents)
    except UnicodeDecodeError as exc:
        raise ValueError("Unable to decode ASCII STL; file is malformed.") from exc


def _looks_like_binary_stl(contents: bytes) -> bool:
    if len(contents) < 84:
        return False

    triangle_count = struct.unpack_from("<I", contents, 80)[0]
    expected_size = 84 + triangle_count * 50
    return expected_size == len(contents)


def _parse_binary_stl_metadata(contents: bytes) -> GeometryMetadata:
    if len(contents) < 84:
        raise ValueError("Binary STL is malformed: missing header or triangle count.")

    triangle_count = struct.unpack_from("<I", contents, 80)[0]
    expected_size = 84 + triangle_count * 50
    if expected_size != len(contents):
        raise ValueError(
            "Binary STL is malformed: triangle count does not match file size."
        )
    if triangle_count == 0:
        raise ValueError("STL geometry contains no triangles.")

    triangles: list[list[tuple[float, float, float]]] = []
    offset = 84
    for triangle_index in range(triangle_count):
        values = struct.unpack_from("<12fH", contents, offset)
        normal = values[0:3]
        vertices = [
            (values[3], values[4], values[5]),
            (values[6], values[7], values[8]),
            (values[9], values[10], values[11]),
        ]
        _validate_finite_values(normal, f"triangle {triangle_index + 1} normal")
        for vertex_index, vertex in enumerate(vertices, start=1):
            _validate_finite_values(
                vertex, f"triangle {triangle_index + 1} vertex {vertex_index}"
            )
        triangles.append(vertices)
        offset += 50

    return _metadata_from_triangles("stl-binary", triangles)


def _parse_ascii_stl_metadata(contents: bytes) -> GeometryMetadata:
    if b"\x00" in contents:
        raise ValueError("STL file is malformed; ASCII STL contains null bytes.")

    text = contents.decode("utf-8-sig")
    if not text.strip():
        raise ValueError("STL file is empty.")
    if not re.search(r"^\s*solid\b", text):
        raise ValueError("ASCII STL is malformed: missing solid header.")

    triangles: list[list[tuple[float, float, float]]] = []
    current_vertices: list[tuple[float, float, float]] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        parts = line.strip().split()
        if not parts:
            continue
        keyword = parts[0].lower()
        if keyword == "vertex":
            if len(parts) != 4:
                raise ValueError(
                    f"ASCII STL is malformed: vertex on line {line_number} must have 3 coordinates."
                )
            try:
                vertex = tuple(float(value) for value in parts[1:4])
            except ValueError as exc:
                raise ValueError(
                    f"ASCII STL is malformed: vertex on line {line_number} has invalid coordinates."
                ) from exc
            _validate_finite_values(vertex, f"line {line_number} vertex")
            current_vertices.append(vertex)
            continue
        if keyword == "facet" and len(parts) >= 5 and parts[1].lower() == "normal":
            try:
                normal = tuple(float(value) for value in parts[2:5])
            except ValueError as exc:
                raise ValueError(
                    f"ASCII STL is malformed: facet normal on line {line_number} has invalid coordinates."
                ) from exc
            _validate_finite_values(normal, f"line {line_number} facet normal")
            continue
        if keyword == "endfacet":
            if len(current_vertices) != 3:
                raise ValueError(
                    f"ASCII STL is malformed: facet ending on line {line_number} has {len(current_vertices)} vertices; expected 3."
                )
            triangles.append(current_vertices)
            current_vertices = []

    if current_vertices:
        raise ValueError("ASCII STL is malformed: final facet was not closed.")
    if not triangles:
        raise ValueError("STL geometry contains no triangles.")

    return _metadata_from_triangles("stl-ascii", triangles)


def _validate_finite_values(values: tuple[float, ...], label: str) -> None:
    if not all(np.isfinite(value) for value in values):
        raise ValueError(f"STL geometry contains non-finite coordinates in {label}.")


def _metadata_from_triangles(
    stl_format: Literal["stl-ascii", "stl-binary"],
    triangles: list[list[tuple[float, float, float]]],
) -> GeometryMetadata:
    vertices = np.asarray(triangles, dtype=np.float64)
    edge_a = vertices[:, 1, :] - vertices[:, 0, :]
    edge_b = vertices[:, 2, :] - vertices[:, 0, :]
    double_areas = np.linalg.norm(np.cross(edge_a, edge_b), axis=1)
    degenerate_indexes = np.where(double_areas <= 0.0)[0]
    if degenerate_indexes.size:
        triangle_number = int(degenerate_indexes[0]) + 1
        raise ValueError(f"STL geometry contains a degenerate triangle at index {triangle_number}.")

    flat_vertices = vertices.reshape((-1, 3))
    min_bounds = flat_vertices.min(axis=0)
    max_bounds = flat_vertices.max(axis=0)
    extents = max_bounds - min_bounds
    if np.any(extents <= 0.0):
        raise ValueError(
            "STL geometry is degenerate: bounding box must have positive x, y, and z extents."
        )

    unique_vertices = np.unique(flat_vertices, axis=0)
    return GeometryMetadata(
        format=stl_format,
        triangle_count=len(triangles),
        vertex_count=int(unique_vertices.shape[0]),
        dimensions={"x": float(extents[0]), "y": float(extents[1]), "z": float(extents[2])},
        bounds=GeometryBounds(
            x=(float(min_bounds[0]), float(max_bounds[0])),
            y=(float(min_bounds[1]), float(max_bounds[1])),
            z=(float(min_bounds[2]), float(max_bounds[2])),
        ),
    )


def _persist_uploaded_dataset(uploaded_files: list[UploadedDatasetFile]) -> str:
    dataset_id = str(uuid.uuid4())
    dataset_dir = get_settings().upload_storage_root / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=False)

    # Minimal local persistence only. A durable datasets table/record should own
    # this ID, metadata, asset paths, and lifecycle once planned dataset resources
    # from API_CONTRACTS.md are implemented.
    for uploaded_file in uploaded_files:
        output_path = dataset_dir / _safe_storage_file_name(uploaded_file.file_name)
        output_path.write_bytes(uploaded_file.contents)

    return dataset_id


def _persist_intake_assets(
    slot: DatasetSlot,
    uploaded_files: list[UploadedDatasetFile],
    generated_files: list[UploadedDatasetFile],
    *,
    existing_dataset_id: str | None,
) -> str:
    if slot in {"npyVolume", "stlCad"} and existing_dataset_id:
        dataset_dir = get_settings().upload_storage_root / existing_dataset_id
        if not dataset_dir.is_dir():
            raise HTTPException(status_code=404, detail="Dataset not found.")

        upload = uploaded_files[0]
        output_path = (
            dataset_dir / "override_volume.npy"
            if slot == "npyVolume"
            else dataset_dir / _safe_storage_file_name(upload.file_name)
        )
        output_path.write_bytes(upload.contents)
        if slot == "npyVolume":
            _load_cached_original_volume.cache_clear()
        return existing_dataset_id

    return _persist_uploaded_dataset(uploaded_files + generated_files)


def _expected_dimensions(
    expected_x: int | None,
    expected_y: int | None,
    expected_z: int | None,
) -> DatasetDimensions | None:
    if expected_x is None and expected_y is None and expected_z is None:
        return None

    if expected_x is None or expected_y is None:
        raise HTTPException(
            status_code=422,
            detail="expected_x and expected_y are required when validating a .npy override.",
        )

    return DatasetDimensions(x=expected_x, y=expected_y, z=expected_z)


def format_dimensions(dimensions: DatasetDimensions) -> str:
    return " x ".join(
        str(value)
        for value in (dimensions.x, dimensions.y, dimensions.z)
        if value is not None
    )


def _safe_storage_file_name(file_name: str) -> str:
    name = Path(file_name).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return safe_name or "unnamed"


def _get_existing_cached_volume(dataset_id: str) -> np.ndarray:
    storage_root = get_settings().upload_storage_root
    dataset_dir = storage_root / dataset_id

    if not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="Dataset not found.")

    return _load_cached_original_volume(str(storage_root), dataset_id)


@lru_cache(maxsize=4)
def _load_cached_original_volume(storage_root: str, dataset_id: str) -> np.ndarray:
    # Process-local convenience cache for interactive slice browsing. It is lost on
    # server restart and is not coherent across multi-worker deployments.
    return _load_persisted_original_volume(Path(storage_root) / dataset_id)


def _load_persisted_original_volume(dataset_dir: Path) -> np.ndarray:
    override_path = dataset_dir / "override_volume.npy"
    if override_path.is_file():
        return _as_zyx_volume(np.load(override_path, allow_pickle=False))

    normalized_path = dataset_dir / "normalized_volume.npy"
    if normalized_path.is_file():
        return _as_zyx_volume(np.load(normalized_path, allow_pickle=False))

    npy_files = sorted(dataset_dir.glob("*.npy"), key=lambda path: _natural_sort_key(path.name))

    if npy_files:
        return _as_zyx_volume(np.load(npy_files[0], allow_pickle=False))

    tiff_files = sorted(
        [*dataset_dir.glob("*.tif"), *dataset_dir.glob("*.tiff")],
        key=lambda path: _natural_sort_key(path.name),
    )

    if tiff_files:
        arrays = [
            _load_tiff_volume_from_bytes(tiff_file.read_bytes())
            for tiff_file in tiff_files
        ]
        return np.concatenate(arrays, axis=0)

    raise HTTPException(status_code=404, detail="No original CT volume asset found.")


def _load_npy_volume_from_bytes(contents: bytes) -> np.ndarray:
    return np.load(BytesIO(contents), allow_pickle=False)


def _load_tiff_volume_from_bytes(contents: bytes) -> np.ndarray:
    with tifffile.TiffFile(BytesIO(contents)) as tiff:
        return _as_zyx_volume(tiff.asarray())


def _load_tiff_stack_from_uploads(uploads: list[UploadedDatasetFile]) -> np.ndarray:
    sorted_uploads = sorted(uploads, key=lambda upload: _natural_sort_key(upload.file_name))
    arrays = [
        _load_tiff_volume_from_bytes(upload.contents)
        for upload in sorted_uploads
    ]
    return np.concatenate(arrays, axis=0)


def _npy_bytes_from_array(array: np.ndarray) -> bytes:
    buffer = BytesIO()
    np.save(buffer, array)
    return buffer.getvalue()


def _normalize_volume_for_storage(volume: np.ndarray) -> np.ndarray:
    volume_float = np.asarray(volume, dtype=np.float32)
    finite = volume_float[np.isfinite(volume_float)]

    if finite.size == 0:
        return np.zeros(volume_float.shape, dtype=np.float32)

    min_value = float(np.min(finite))
    max_value = float(np.max(finite))

    if np.isclose(min_value, max_value):
        return np.zeros(volume_float.shape, dtype=np.float32)

    volume_float -= min_value
    volume_float /= max_value - min_value
    np.nan_to_num(volume_float, copy=False, nan=0.0, posinf=1.0, neginf=0.0)
    np.clip(volume_float, 0.0, 1.0, out=volume_float)
    return volume_float


def _as_zyx_volume(array: np.ndarray) -> np.ndarray:
    if array.ndim == 2:
        return array[np.newaxis, :, :]
    if array.ndim == 3:
        return array

    raise ValueError("Expected a 2D slice or 3D CT volume.")


def _axis_size(volume: np.ndarray, axis: SliceAxis) -> int:
    if axis == "x":
        return volume.shape[2]
    if axis == "y":
        return volume.shape[1]
    return volume.shape[0]


def _extract_slice(volume: np.ndarray, axis: SliceAxis, index: int) -> np.ndarray:
    if axis == "x":
        return volume[:, :, index]
    if axis == "y":
        return volume[:, index, :]
    return volume[index, :, :]


def _normalize_to_uint8(image: np.ndarray) -> np.ndarray:
    image_float = np.asarray(image, dtype=np.float32)
    finite = image_float[np.isfinite(image_float)]

    if finite.size == 0:
        return np.zeros(image_float.shape, dtype=np.uint8)

    min_value = float(np.min(finite))
    max_value = float(np.max(finite))

    if np.isclose(min_value, max_value):
        return np.zeros(image_float.shape, dtype=np.uint8)

    normalized = (image_float - min_value) / (max_value - min_value)
    normalized = np.nan_to_num(normalized, nan=0.0, posinf=1.0, neginf=0.0)
    return np.clip(normalized * 255.0, 0, 255).astype(np.uint8)


def _finite_min_max(image: np.ndarray) -> tuple[float, float]:
    image_float = np.asarray(image, dtype=np.float32)
    finite = image_float[np.isfinite(image_float)]

    if finite.size == 0:
        return 0.0, 0.0

    return float(np.min(finite)), float(np.max(finite))


def _encode_grayscale_png(image: np.ndarray) -> bytes:
    if image.ndim != 2:
        raise ValueError("PNG encoding expects a 2D grayscale image.")

    height, width = image.shape
    raw_rows = b"".join(b"\x00" + image[row].tobytes() for row in range(height))

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw_rows))
        + chunk(b"IEND", b"")
    )


def _dimensions_from_shape(shape: tuple[int, ...]) -> DatasetDimensions:
    if len(shape) == 2:
        return DatasetDimensions(x=shape[1], y=shape[0], z=None)

    return DatasetDimensions(x=shape[2], y=shape[1], z=shape[0])


def _natural_sort_key(value: str) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", value)
    ]


def _extract_tiff_metadata(tiff: tifffile.TiffFile) -> dict[str, Any]:
    if not tiff.pages:
        return {}

    metadata: dict[str, Any] = {}
    first_page = tiff.pages[0]

    for tag in first_page.tags.values():
        value = _json_safe_tiff_value(tag.value)
        if value is not None:
            metadata[tag.name] = value

    if tiff.imagej_metadata:
        metadata["ImageJMetadata"] = _json_safe_tiff_value(tiff.imagej_metadata)

    if tiff.ome_metadata:
        metadata["OMEMetadata"] = tiff.ome_metadata

    return metadata


def _json_safe_tiff_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, tuple | list):
        return [_json_safe_tiff_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_tiff_value(item) for key, item in value.items()}

    return str(value)


def _voxel_size_micron_from_tiff_metadata(metadata: dict[str, Any]) -> float | None:
    x_resolution = _resolution_value(metadata.get("XResolution"))
    y_resolution = _resolution_value(metadata.get("YResolution"))
    resolution_unit = metadata.get("ResolutionUnit")
    microns_per_unit = _microns_per_resolution_unit(resolution_unit)

    if x_resolution is None or microns_per_unit is None:
        return None

    x_voxel_size = microns_per_unit / x_resolution

    if y_resolution is None:
        return x_voxel_size

    y_voxel_size = microns_per_unit / y_resolution

    if not np.isclose(x_voxel_size, y_voxel_size):
        return None

    return float(x_voxel_size)


def _resolution_value(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value) if value > 0 else None

    if isinstance(value, list | tuple) and len(value) == 2:
        numerator, denominator = value
        if isinstance(numerator, int | float) and isinstance(denominator, int | float):
            if denominator == 0:
                return None
            result = float(numerator) / float(denominator)
            return result if result > 0 else None

    return None


def _microns_per_resolution_unit(value: Any) -> float | None:
    if value in (2, "INCH", "inch"):
        return 25400.0
    if value in (3, "CENTIMETER", "centimeter", "cm"):
        return 10000.0
    return None


def _extract_json_metadata(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        for key in ("metadata", "meta", "properties"):
            metadata = value.get(key)
            if isinstance(metadata, dict):
                return metadata
    return None


def _find_numeric_metadata(value: Any, target_key: str) -> float | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == target_key and isinstance(item, int | float):
                return float(item)
            found = _find_numeric_metadata(item, target_key)
            if found is not None:
                return found

    if isinstance(value, list):
        for item in value:
            found = _find_numeric_metadata(item, target_key)
            if found is not None:
                return found

    return None
