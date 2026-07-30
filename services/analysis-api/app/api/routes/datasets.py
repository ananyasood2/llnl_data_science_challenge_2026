"""Dataset intake endpoints."""

from __future__ import annotations

import json
import re
import struct
import uuid
import zlib
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, NamedTuple

import numpy as np
import tifffile
from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from skimage.filters import threshold_otsu
from skimage.measure import label
from skimage.morphology import skeletonize
from scipy import ndimage

from lattice_pipeline.defects import DefectConfig, classify_defects
from lattice_pipeline.io import load_design_graph

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
DefectJobStatus = Literal["not_run", "running", "complete", "failed"]
DefectCategory = Literal["missing", "uncertain", "thin", "thick"]
DEFECT_CATEGORY_COLORS: dict[str, tuple[int, int, int]] = {
    "missing": (231, 76, 60),
    "uncertain": (245, 158, 11),
    "thin": (59, 130, 246),
    "thick": (139, 92, 246),
}


class ThresholdPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float
    axis: SliceAxis
    index: int


HistogramScope = Literal["volume", "slice"]


class IntensityHistogramRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float
    scope: HistogramScope = "volume"
    axis: SliceAxis = "z"
    index: int | None = None


class IntensityHistogramResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    scope: HistogramScope
    axis: SliceAxis | None
    index: int | None
    bin_edges: list[float]
    bin_counts: list[int]
    threshold: float
    foreground_voxel_count: int
    background_voxel_count: int
    foreground_percentage: float
    background_percentage: float


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


AnalysisJobStatus = Literal[
    "queued", "segmenting", "skeletonizing", "complete", "failed"
]


class StartAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = None
    dataset_name: str | None = None
    voxel_size_micron: float | None = None


class ArtifactSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str


class SegmentationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float
    foreground_voxel_count: int
    background_voxel_count: int
    dimensions: DatasetDimensions
    mask_path: str
    slice_preview_path: str
    summary_path: str


class VoxelBounds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: tuple[int, int] | None
    y: tuple[int, int] | None
    z: tuple[int, int] | None
    unit: Literal["pixels/voxels", "microns"]


class SkeletonSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skeleton_voxel_count: int
    connected_components: int
    endpoints: int
    branch_points: int
    disconnected_regions: int
    bounds: VoxelBounds
    skeleton_path: str
    slice_preview_path: str
    summary_path: str


class AnalysisJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    project_id: str
    dataset_id: str
    dataset_name: str | None
    status: AnalysisJobStatus
    progress: list[AnalysisJobStatus]
    segmentation: SegmentationSummary | None = None
    skeletonization: SkeletonSummary | None = None
    artifacts: dict[str, ArtifactSummary] = Field(default_factory=dict)
    error: str | None = None
    created_at: str
    updated_at: str
    scale_unit: Literal["pixels/voxels", "microns"]


class ArtifactManifestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    project_id: str
    graph_reference_available: bool = False
    graph_reference_file_name: str | None = None
    artifacts: dict[str, ArtifactSummary]


class DatasetManifestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    graph_reference_available: bool = False
    graph_reference_file_name: str | None = None
    assets: dict[str, list[str]] = Field(default_factory=dict)


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
    defect_category: str | None = None
    defect_status: Literal["none", "flagged", "not_run"] = "not_run"


class DefectSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    status: DefectJobStatus
    total_flagged_elements: int = 0
    total_flagged_voxels: int = 0
    category_counts: dict[str, int] = Field(default_factory=dict)
    reference_available: bool = False
    reference_message: str
    defect_artifact_path: str | None = None
    summary_path: str | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


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
            response=response,
            existing_dataset_id=dataset_id,
        )
        manifest = _load_dataset_manifest(
            get_settings().upload_storage_root / persisted_dataset_id
        )
        return response.model_copy(
            update={
                "dataset_id": persisted_dataset_id,
                "graph_reference_available": manifest.get(
                    "graph_reference_available", False
                ),
                "graph_reference_file_name": manifest.get("graph_reference_file_name"),
            }
        )
    finally:
        for upload in files:
            await upload.close()


@router.get("/{dataset_id}/manifest", response_model=DatasetManifestResponse)
async def get_dataset_manifest(dataset_id: str) -> DatasetManifestResponse:
    """Return persisted dataset intake metadata."""
    dataset_dir = _get_existing_dataset_dir(dataset_id)
    manifest = _load_dataset_manifest(dataset_dir)
    graph_path = _find_graph_json_path(dataset_dir)
    assets = manifest.get("assets")
    return DatasetManifestResponse(
        dataset_id=dataset_id,
        graph_reference_available=graph_path is not None,
        graph_reference_file_name=graph_path.name if graph_path else None,
        assets=assets if isinstance(assets, dict) else {},
    )


@router.get("/{dataset_id}/slices/{axis}/{index}")
async def get_dataset_slice(
    dataset_id: str,
    axis: SliceAxis,
    index: int,
    view: SliceView = Query("original"),
) -> Response:
    """Return a normalized PNG slice for a persisted dataset volume."""
    storage_root = get_settings().upload_storage_root
    dataset_dir = storage_root / dataset_id

    if not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="Dataset not found.")

    if view in {"segmentation", "skeleton"}:
        artifact_path = dataset_dir / f"{view}.npy"
        if not artifact_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"{view} view has not been generated for this dataset.",
            )
        volume = _as_zyx_volume(np.load(artifact_path, allow_pickle=False))
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


@router.post("/{dataset_id}/defect-jobs", response_model=DefectSummaryResponse)
async def start_defect_detection_job(dataset_id: str) -> DefectSummaryResponse:
    """Run reference-aware defect detection from persisted segmentation/skeleton artifacts."""
    dataset_dir = _get_existing_dataset_dir(dataset_id)
    job = _base_defect_record(dataset_id, "running")
    _write_json(dataset_dir / "defect_job.json", job)

    try:
        result, summary = _run_defect_detection_agent(dataset_dir, dataset_id)
        job.update(
            {
                "status": "complete",
                "total_flagged_elements": summary["total_flagged_elements"],
                "total_flagged_voxels": summary["total_flagged_voxels"],
                "category_counts": summary["category_counts"],
                "reference_available": summary["reference_available"],
                "reference_message": summary["reference_message"],
                "defect_artifact_path": "defects.json",
                "summary_path": "defect_summary.json",
                "error": None,
            }
        )
        _write_json(dataset_dir / "defects.json", result)
        _write_json(dataset_dir / "defect_summary.json", summary)
    except Exception as exc:
        job.update(
            {
                "status": "failed",
                "error": str(exc),
                "reference_available": _find_graph_json_path(dataset_dir) is not None,
                "reference_message": str(exc),
            }
        )

    job["updated_at"] = _utc_now()
    _write_json(dataset_dir / "defect_job.json", job)
    return DefectSummaryResponse.model_validate(job)


@router.get("/{dataset_id}/defect-jobs/latest", response_model=DefectSummaryResponse)
async def get_latest_defect_job(dataset_id: str) -> DefectSummaryResponse:
    dataset_dir = _get_existing_dataset_dir(dataset_id)
    job_path = dataset_dir / "defect_job.json"
    if not job_path.is_file():
        return _not_run_defect_response(dataset_id, dataset_dir)
    return DefectSummaryResponse.model_validate(json.loads(job_path.read_text()))


@router.get("/{dataset_id}/defect-slices/{axis}/{index}")
async def get_defect_slice(
    dataset_id: str,
    axis: SliceAxis,
    index: int,
    opacity: float = Query(0.55, ge=0.0, le=1.0),
) -> Response:
    """Return a PNG original slice with persisted defect markers overlaid."""
    dataset_dir = _get_existing_dataset_dir(dataset_id)
    job = _load_latest_defect_record(dataset_dir)
    if job["status"] != "complete":
        raise HTTPException(status_code=409, detail=f"Defect detection is {job['status']}.")

    volume = _load_cached_original_volume(str(get_settings().upload_storage_root), dataset_id)
    max_index = _axis_size(volume, axis) - 1
    if index < 0 or index > max_index:
        raise HTTPException(
            status_code=400,
            detail=f"Slice index {index} is out of range for axis {axis}; expected 0..{max_index}.",
        )

    result = _load_defect_result(dataset_dir)
    base = _normalize_to_uint8(_extract_slice(volume, axis, index))
    rgb = np.repeat(base[:, :, None], 3, axis=2)
    slice_counts = _overlay_defects_on_slice(rgb, result.get("defects", []), axis, index, opacity)
    png = _encode_rgb_png(rgb)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "X-Slice-Axis": axis,
            "X-Slice-Index": str(index),
            "X-View": "defects",
            "X-Defect-Slice-Counts": json.dumps(slice_counts, sort_keys=True),
        },
    )


@router.post("/{dataset_id}/analysis-jobs", response_model=AnalysisJobResponse)
async def start_analysis_job(
    dataset_id: str,
    request: StartAnalysisRequest,
) -> AnalysisJobResponse:
    """Run segmentation and skeletonization for a persisted CT dataset."""
    dataset_dir = _get_existing_dataset_dir(dataset_id)
    job_id = str(uuid.uuid4())
    project_id = _ensure_project_id(dataset_dir, request.project_id)
    scale_unit: Literal["pixels/voxels", "microns"] = (
        "microns" if request.voxel_size_micron is not None else "pixels/voxels"
    )
    job = _base_job_record(
        job_id=job_id,
        project_id=project_id,
        dataset_id=dataset_id,
        dataset_name=request.dataset_name,
        scale_unit=scale_unit,
    )
    graph_path = _find_graph_json_path(dataset_dir)
    if graph_path is not None:
        job["artifacts"]["registered_graph"] = {"path": graph_path.name}
    _write_json(dataset_dir / "analysis_job.json", job)

    try:
        job["status"] = "segmenting"
        job["progress"].append("segmenting")
        job["updated_at"] = _utc_now()
        _write_json(dataset_dir / "analysis_job.json", job)

        volume = _load_persisted_original_volume(dataset_dir)
        segmentation = _run_segmentation_agent(dataset_dir, volume)
        job["segmentation"] = segmentation
        job["artifacts"].update(
            {
                "segmentation_mask": {"path": segmentation["mask_path"]},
                "segmentation_summary": {"path": segmentation["summary_path"]},
            }
        )
        del volume

        job["status"] = "skeletonizing"
        job["progress"].append("skeletonizing")
        job["updated_at"] = _utc_now()
        _write_json(dataset_dir / "analysis_job.json", job)

        skeletonization = _run_skeletonization_agent(dataset_dir, scale_unit)
        job["skeletonization"] = skeletonization
        job["artifacts"].update(
            {
                "skeleton": {"path": skeletonization["skeleton_path"]},
                "skeleton_summary": {"path": skeletonization["summary_path"]},
            }
        )
        job["status"] = "complete"
        job["progress"].append("complete")
    except Exception as exc:
        job["status"] = "failed"
        job["progress"].append("failed")
        job["error"] = str(exc)

    job["updated_at"] = _utc_now()
    _write_json(dataset_dir / "analysis_job.json", job)
    return AnalysisJobResponse.model_validate(job)


@router.get("/{dataset_id}/analysis-jobs/latest", response_model=AnalysisJobResponse)
async def get_latest_analysis_job(dataset_id: str) -> AnalysisJobResponse:
    dataset_dir = _get_existing_dataset_dir(dataset_id)
    job_path = dataset_dir / "analysis_job.json"
    if not job_path.is_file():
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return AnalysisJobResponse.model_validate(json.loads(job_path.read_text()))


@router.get("/{dataset_id}/artifacts", response_model=ArtifactManifestResponse)
async def list_dataset_artifacts(dataset_id: str) -> ArtifactManifestResponse:
    dataset_dir = _get_existing_dataset_dir(dataset_id)
    job = _load_latest_job_record(dataset_dir)
    graph_path = _find_graph_json_path(dataset_dir)
    return ArtifactManifestResponse(
        dataset_id=dataset_id,
        project_id=job["project_id"],
        graph_reference_available=graph_path is not None,
        graph_reference_file_name=graph_path.name if graph_path else None,
        artifacts=job["artifacts"],
    )


@router.get("/{dataset_id}/artifacts/{artifact_name}")
async def get_dataset_artifact(dataset_id: str, artifact_name: str) -> FileResponse:
    dataset_dir = _get_existing_dataset_dir(dataset_id)
    job = _load_latest_job_record(dataset_dir)
    artifact = job["artifacts"].get(artifact_name)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found.")

    artifact_path = dataset_dir / artifact["path"]
    if not artifact_path.is_file() or artifact_path.parent != dataset_dir:
        raise HTTPException(status_code=404, detail="Artifact file not found.")

    return FileResponse(
        artifact_path,
        media_type=_artifact_media_type(artifact_path),
        filename=artifact_path.name,
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


@router.post("/{dataset_id}/intensity-histogram", response_model=IntensityHistogramResponse)
async def get_intensity_histogram(
    dataset_id: str,
    request: IntensityHistogramRequest,
) -> IntensityHistogramResponse:
    """Return a compact intensity histogram for the persisted normalized volume."""
    volume = _get_existing_cached_volume(dataset_id)
    histogram_source: np.ndarray = volume
    axis: SliceAxis | None = None
    index: int | None = None

    if request.scope == "slice":
        if request.index is None:
            raise HTTPException(
                status_code=422,
                detail="Slice histogram requests require an index.",
            )

        max_index = _axis_size(volume, request.axis) - 1

        if request.index < 0 or request.index > max_index:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Slice index {request.index} is out of range for axis "
                    f"{request.axis}; expected 0..{max_index}."
                ),
            )

        histogram_source = _extract_slice(volume, request.axis, request.index)
        axis = request.axis
        index = request.index

    counts, edges = np.histogram(histogram_source, bins=256, range=(0.0, 1.0))
    foreground_voxel_count = int(np.count_nonzero(histogram_source > request.threshold))
    background_voxel_count = int(histogram_source.size - foreground_voxel_count)
    total_voxels = max(int(histogram_source.size), 1)
    foreground_percentage = (foreground_voxel_count / total_voxels) * 100.0

    return IntensityHistogramResponse(
        dataset_id=dataset_id,
        scope=request.scope,
        axis=axis,
        index=index,
        bin_edges=[float(edge) for edge in edges],
        bin_counts=[int(count) for count in counts],
        threshold=request.threshold,
        foreground_voxel_count=foreground_voxel_count,
        background_voxel_count=background_voxel_count,
        foreground_percentage=foreground_percentage,
        background_percentage=100.0 - foreground_percentage,
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
    defect_category = _defect_category_at_coordinate(
        get_settings().upload_storage_root / dataset_id,
        request.x,
        request.y,
        request.z,
    )

    return VoxelProbeResponse(
        x=request.x,
        y=request.y,
        z=request.z,
        intensity=intensity,
        mask_value=1 if intensity > request.threshold else 0,
        defect_category=defect_category,
        defect_status=(
            "flagged"
            if defect_category
            else "none"
            if (get_settings().upload_storage_root / dataset_id / "defects.json").is_file()
            else "not_run"
        ),
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
            valid=False,
            slot=slot,
            file_names=file_names,
            file_type=suffix.lstrip("."),
            dimensions=None,
            intensity_range=None,
            embedded_metadata=None,
            voxel_size_micron=None,
            warnings=[
                "GraphML parsing is not implemented yet.",
            ],
            errors=["Upload a registered graph JSON for reference-based detection."],
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

    stored_files = []
    for uploaded_file in uploaded_files:
        output_path = dataset_dir / _safe_storage_file_name(uploaded_file.file_name)
        output_path.write_bytes(uploaded_file.contents)
        stored_files.append(output_path.name)

    _write_dataset_manifest(
        dataset_dir,
        {
            "dataset_id": dataset_id,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "assets": {"uploaded": stored_files},
            "graph_reference_available": False,
            "graph_reference_file_name": None,
            "graph_reference_metadata": None,
        },
    )

    return dataset_id


def _persist_intake_assets(
    slot: DatasetSlot,
    uploaded_files: list[UploadedDatasetFile],
    generated_files: list[UploadedDatasetFile],
    *,
    response: DatasetIntakeResponse,
    existing_dataset_id: str | None,
) -> str:
    if slot == "graphJson" and not existing_dataset_id:
        raise HTTPException(
            status_code=422,
            detail="Graph JSON uploads must be associated with an existing CT dataset.",
        )

    if slot in {"npyVolume", "stlCad", "graphJson"} and existing_dataset_id:
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
        _record_intake_in_manifest(dataset_dir, slot, output_path.name, response)
        return existing_dataset_id

    dataset_id = _persist_uploaded_dataset(uploaded_files + generated_files)
    dataset_dir = get_settings().upload_storage_root / dataset_id
    for uploaded_file in uploaded_files:
        _record_intake_in_manifest(
            dataset_dir,
            slot,
            _safe_storage_file_name(uploaded_file.file_name),
            response,
        )
    for generated_file in generated_files:
        _record_intake_in_manifest(
            dataset_dir,
            "npyVolume",
            _safe_storage_file_name(generated_file.file_name),
            response,
        )
    return dataset_id


def _get_existing_dataset_dir(dataset_id: str) -> Path:
    dataset_dir = get_settings().upload_storage_root / dataset_id
    if not dataset_dir.is_dir():
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return dataset_dir


def _ensure_project_id(dataset_dir: Path, candidate: str | None) -> str:
    project_path = dataset_dir / "project.json"
    if project_path.is_file():
        data = json.loads(project_path.read_text())
        project_id = data.get("project_id")
        if isinstance(project_id, str) and project_id:
            return project_id

    project_id = (
        candidate
        if candidate and candidate.lower() != "pending"
        else f"inspection-{uuid.uuid4()}"
    )
    _write_json(
        project_path,
        {
            "project_id": project_id,
            "created_at": _utc_now(),
        },
    )
    return project_id


def _base_job_record(
    *,
    job_id: str,
    project_id: str,
    dataset_id: str,
    dataset_name: str | None,
    scale_unit: Literal["pixels/voxels", "microns"],
) -> dict[str, Any]:
    now = _utc_now()
    return {
        "job_id": job_id,
        "project_id": project_id,
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "status": "queued",
        "progress": ["queued"],
        "segmentation": None,
        "skeletonization": None,
        "artifacts": {},
        "error": None,
        "created_at": now,
        "updated_at": now,
        "scale_unit": scale_unit,
    }


def _run_segmentation_agent(dataset_dir: Path, volume: np.ndarray) -> dict[str, Any]:
    threshold = _choose_initial_threshold(volume)
    mask = volume > threshold
    foreground_voxel_count = int(np.count_nonzero(mask))
    background_voxel_count = int(mask.size - foreground_voxel_count)
    if foreground_voxel_count == 0:
        raise ValueError(
            f"Segmentation threshold {threshold:.6g} produced no foreground voxels."
        )

    mask_path = dataset_dir / "segmentation.npy"
    preview_path = dataset_dir / "segmentation_slice_preview.png"
    summary_path = dataset_dir / "segmentation_summary.json"
    middle_z = mask.shape[0] // 2
    np.save(mask_path, mask)
    preview_path.write_bytes(
        _encode_grayscale_png(_extract_slice(mask, "z", middle_z).astype(np.uint8) * 255)
    )
    summary = {
        "threshold": threshold,
        "foreground_voxel_count": foreground_voxel_count,
        "background_voxel_count": background_voxel_count,
        "dimensions": {
            "x": int(mask.shape[2]),
            "y": int(mask.shape[1]),
            "z": int(mask.shape[0]),
        },
        "mask_path": "segmentation.npy",
        "slice_preview_path": "segmentation_slice_preview.png",
        "summary_path": "segmentation_summary.json",
    }
    _write_json(summary_path, summary)
    return summary


def _choose_initial_threshold(volume: np.ndarray) -> float:
    finite = np.asarray(volume[np.isfinite(volume)], dtype=np.float32)
    if finite.size == 0:
        raise ValueError("Volume contains no finite intensity values.")
    if np.isclose(float(finite.min()), float(finite.max())):
        raise ValueError("Volume has no usable intensity contrast for segmentation.")

    sample = finite
    max_samples = 2_000_000
    if finite.size > max_samples:
        step = max(1, finite.size // max_samples)
        sample = finite[::step]

    return float(threshold_otsu(sample))


def _run_skeletonization_agent(
    dataset_dir: Path,
    scale_unit: Literal["pixels/voxels", "microns"],
) -> dict[str, Any]:
    mask_path = dataset_dir / "segmentation.npy"
    if not mask_path.is_file():
        raise ValueError("Segmentation mask is missing; skeletonization was not run.")

    mask = np.load(mask_path, allow_pickle=False)
    skeleton = skeletonize(mask > 0)
    skeleton_voxel_count = int(np.count_nonzero(skeleton))
    labeled = label(skeleton, connectivity=3)
    connected_components = int(labeled.max())
    endpoints, branch_points = _count_skeleton_nodes(skeleton)
    bounds = _voxel_bounds(skeleton, scale_unit)

    skeleton_path = dataset_dir / "skeleton.npy"
    preview_path = dataset_dir / "skeleton_slice_preview.png"
    summary_path = dataset_dir / "skeleton_summary.json"
    middle_z = skeleton.shape[0] // 2
    np.save(skeleton_path, skeleton)
    preview_path.write_bytes(
        _encode_grayscale_png(
            _extract_slice(skeleton, "z", middle_z).astype(np.uint8) * 255
        )
    )
    summary = {
        "skeleton_voxel_count": skeleton_voxel_count,
        "connected_components": connected_components,
        "endpoints": endpoints,
        "branch_points": branch_points,
        "disconnected_regions": max(0, connected_components - 1),
        "bounds": bounds,
        "skeleton_path": "skeleton.npy",
        "slice_preview_path": "skeleton_slice_preview.png",
        "summary_path": "skeleton_summary.json",
    }
    _write_json(summary_path, summary)
    return summary


def _base_defect_record(dataset_id: str, status: DefectJobStatus) -> dict[str, Any]:
    now = _utc_now()
    graph_path = _find_graph_json_path(get_settings().upload_storage_root / dataset_id)
    return {
        "dataset_id": dataset_id,
        "status": status,
        "total_flagged_elements": 0,
        "total_flagged_voxels": 0,
        "category_counts": {},
        "reference_available": graph_path is not None,
        "reference_message": (
            f"Using registered graph reference {graph_path.name}."
            if graph_path
            else "Reference-based detection unavailable: no registered graph JSON was uploaded."
        ),
        "defect_artifact_path": None,
        "summary_path": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }


def _not_run_defect_response(dataset_id: str, dataset_dir: Path) -> DefectSummaryResponse:
    record = _base_defect_record(dataset_id, "not_run")
    record["created_at"] = None
    record["updated_at"] = None
    record["reference_available"] = _find_graph_json_path(dataset_dir) is not None
    if not record["reference_available"]:
        record["reference_message"] = (
            "Reference-based detection unavailable: no registered graph JSON was uploaded."
        )
    return DefectSummaryResponse.model_validate(record)


def _run_defect_detection_agent(
    dataset_dir: Path,
    dataset_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    mask_path = dataset_dir / "segmentation.npy"
    skeleton_path = dataset_dir / "skeleton.npy"
    if not mask_path.is_file() or not skeleton_path.is_file():
        raise ValueError("Segmentation and skeleton artifacts are required before defect detection.")

    graph_path = _find_graph_json_path(dataset_dir)
    if graph_path is None:
        raise ValueError(_missing_graph_reference_message(dataset_dir))

    graph = load_design_graph(graph_path)
    mask = np.load(mask_path, allow_pickle=False)
    skeleton = np.load(skeleton_path, allow_pickle=False)
    distance_map = ndimage.distance_transform_edt(mask > 0)
    nodes = [
        {"id": int(node["id"]), "position": [float(v) for v in node["position"]]}
        for node in graph["junctions"]
    ]
    struts = [
        {
            **strut,
            "id": int(strut["id"]),
            "node_a": int(strut["junction0"]),
            "node_b": int(strut["junction1"]),
        }
        for strut in graph["struts"]
    ]
    result = classify_defects(
        mask,
        skeleton,
        distance_map,
        nodes,
        struts,
        1.0,
        config=DefectConfig(nominal_thickness_um=None),
    )
    supported = set(DEFECT_CATEGORY_COLORS)
    result["defects"] = [
        defect for defect in result["defects"] if defect.get("type") in supported
    ]
    summary = _summarize_defects(dataset_id, result, graph_path)
    result["summary"] = {**result.get("summary", {}), "ui_summary": summary}
    return result, summary


def _summarize_defects(
    dataset_id: str,
    result: dict[str, Any],
    graph_path: Path,
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for defect in result.get("defects", []):
        category = str(defect.get("type"))
        counts[category] = counts.get(category, 0) + 1
    total = sum(counts.values())
    return {
        "dataset_id": dataset_id,
        "status": "complete",
        "total_flagged_elements": total,
        "total_flagged_voxels": total,
        "category_counts": counts,
        "reference_available": True,
        "reference_message": f"Using registered graph reference {graph_path.name}.",
        "defect_artifact_path": "defects.json",
        "summary_path": "defect_summary.json",
        "error": None,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }


def _find_graph_json_path(dataset_dir: Path) -> Path | None:
    manifest = _load_dataset_manifest(dataset_dir)
    graph_file_name = manifest.get("graph_reference_file_name")
    if isinstance(graph_file_name, str) and graph_file_name:
        graph_path = dataset_dir / graph_file_name
        if graph_path.is_file() and graph_path.parent == dataset_dir:
            return graph_path

    candidates = [
        path
        for path in sorted(dataset_dir.glob("*.json"), key=lambda item: _natural_sort_key(item.name))
        if path.name not in {
            "analysis_job.json",
            "dataset_manifest.json",
            "defect_job.json",
            "defect_summary.json",
            "project.json",
            "segmentation_summary.json",
            "skeleton_summary.json",
            "defects.json",
        }
    ]
    return candidates[0] if candidates else None


def _load_dataset_manifest(dataset_dir: Path) -> dict[str, Any]:
    manifest_path = dataset_dir / "dataset_manifest.json"
    if not manifest_path.is_file():
        return {
            "dataset_id": dataset_dir.name,
            "assets": {},
            "graph_reference_available": False,
            "graph_reference_file_name": None,
            "graph_reference_metadata": None,
        }
    try:
        data = json.loads(manifest_path.read_text())
    except json.JSONDecodeError:
        return {
            "dataset_id": dataset_dir.name,
            "assets": {},
            "graph_reference_available": False,
            "graph_reference_file_name": None,
            "graph_reference_metadata": None,
        }
    return data if isinstance(data, dict) else {}


def _write_dataset_manifest(dataset_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = _utc_now()
    _write_json(dataset_dir / "dataset_manifest.json", manifest)


def _record_intake_in_manifest(
    dataset_dir: Path,
    slot: DatasetSlot,
    file_name: str,
    response: DatasetIntakeResponse,
) -> None:
    manifest = _load_dataset_manifest(dataset_dir)
    manifest.setdefault("dataset_id", dataset_dir.name)
    manifest.setdefault("created_at", _utc_now())
    assets = manifest.setdefault("assets", {})
    slot_assets = assets.setdefault(slot, [])
    if file_name not in slot_assets:
        slot_assets.append(file_name)

    if slot == "graphJson":
        manifest["graph_reference_available"] = True
        manifest["graph_reference_file_name"] = file_name
        manifest["graph_reference_metadata"] = response.embedded_metadata

    _write_dataset_manifest(dataset_dir, manifest)


def _missing_graph_reference_message(dataset_dir: Path) -> str:
    job_path = dataset_dir / "analysis_job.json"
    if job_path.is_file():
        try:
            artifact = json.loads(job_path.read_text()).get("artifacts", {}).get(
                "registered_graph"
            )
        except json.JSONDecodeError:
            artifact = None
        if isinstance(artifact, dict) and artifact.get("path"):
            return (
                "Reference-based detection unavailable: registered graph artifact "
                f"{artifact['path']} is recorded for this dataset but the file is missing."
            )
    return "Reference-based detection unavailable: no registered graph JSON was uploaded."


def _load_latest_defect_record(dataset_dir: Path) -> dict[str, Any]:
    job_path = dataset_dir / "defect_job.json"
    if not job_path.is_file():
        raise HTTPException(status_code=409, detail="Defect detection has not been run.")
    return json.loads(job_path.read_text())


def _load_defect_result(dataset_dir: Path) -> dict[str, Any]:
    path = dataset_dir / "defects.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Defect artifact not found.")
    return json.loads(path.read_text())


def _defect_category_at_coordinate(
    dataset_dir: Path,
    x: int,
    y: int,
    z: int,
) -> str | None:
    if not (dataset_dir / "defects.json").is_file():
        return None
    result = _load_defect_result(dataset_dir)
    point = np.asarray([x, y, z], dtype=float)
    for defect in result.get("defects", []):
        category = defect.get("type")
        location = np.asarray(defect.get("location_voxel", []), dtype=float)
        if category in DEFECT_CATEGORY_COLORS and location.shape == (3,):
            if float(np.linalg.norm(location - point)) <= 2.5:
                return str(category)
    return None


def _overlay_defects_on_slice(
    rgb: np.ndarray,
    defects: list[dict[str, Any]],
    axis: SliceAxis,
    index: int,
    opacity: float,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for defect in defects:
        category = str(defect.get("type"))
        color = DEFECT_CATEGORY_COLORS.get(category)
        location = np.asarray(defect.get("location_voxel", []), dtype=float)
        if color is None or location.shape != (3,):
            continue
        plane_value = {"x": location[0], "y": location[1], "z": location[2]}[axis]
        if abs(float(plane_value) - index) > 2.5:
            continue
        row, col = _project_xyz_to_slice_pixel(location, axis)
        _draw_disc(rgb, row, col, color, opacity)
        counts[category] = counts.get(category, 0) + 1
    return counts


def _project_xyz_to_slice_pixel(point_xyz: np.ndarray, axis: SliceAxis) -> tuple[int, int]:
    x, y, z = [int(round(float(value))) for value in point_xyz]
    if axis == "x":
        return z, y
    if axis == "y":
        return z, x
    return y, x


def _draw_disc(
    rgb: np.ndarray,
    row: int,
    col: int,
    color: tuple[int, int, int],
    opacity: float,
    radius: int = 4,
) -> None:
    height, width = rgb.shape[:2]
    r0, r1 = max(0, row - radius), min(height, row + radius + 1)
    c0, c1 = max(0, col - radius), min(width, col + radius + 1)
    if r0 >= r1 or c0 >= c1:
        return
    yy, xx = np.ogrid[r0:r1, c0:c1]
    mask = (yy - row) ** 2 + (xx - col) ** 2 <= radius**2
    patch = rgb[r0:r1, c0:c1]
    patch[mask] = (
        (1.0 - opacity) * patch[mask].astype(float)
        + opacity * np.asarray(color, dtype=float)
    ).astype(np.uint8)


def _count_skeleton_nodes(skeleton: np.ndarray) -> tuple[int, int]:
    padded = np.pad(skeleton.astype(np.uint8, copy=False), 1)
    coordinates = np.argwhere(skeleton)
    endpoints = 0
    branch_points = 0
    for z, y, x in coordinates:
        neighborhood = padded[z : z + 3, y : y + 3, x : x + 3]
        neighbors = int(np.count_nonzero(neighborhood)) - 1
        if neighbors == 1:
            endpoints += 1
        elif neighbors >= 3:
            branch_points += 1
    return endpoints, branch_points


def _voxel_bounds(
    skeleton: np.ndarray,
    unit: Literal["pixels/voxels", "microns"],
) -> dict[str, Any]:
    if not np.any(skeleton):
        return {"x": None, "y": None, "z": None, "unit": unit}
    coords = np.argwhere(skeleton)
    mins = coords.min(axis=0)
    maxs = coords.max(axis=0)
    return {
        "x": (int(mins[2]), int(maxs[2])),
        "y": (int(mins[1]), int(maxs[1])),
        "z": (int(mins[0]), int(maxs[0])),
        "unit": unit,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_latest_job_record(dataset_dir: Path) -> dict[str, Any]:
    job_path = dataset_dir / "analysis_job.json"
    if not job_path.is_file():
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return json.loads(job_path.read_text())


def _artifact_media_type(path: Path) -> str:
    if path.suffix == ".json":
        return "application/json"
    if path.suffix == ".npy":
        return "application/octet-stream"
    if path.suffix == ".png":
        return "image/png"
    return "application/octet-stream"


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


def _encode_rgb_png(image: np.ndarray) -> bytes:
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("PNG encoding expects a 2D RGB image.")

    image_uint8 = np.asarray(image, dtype=np.uint8)
    height, width = image_uint8.shape[:2]
    raw_rows = b"".join(b"\x00" + image_uint8[row].tobytes() for row in range(height))

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
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
