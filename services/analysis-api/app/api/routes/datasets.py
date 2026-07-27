"""Dataset intake endpoints."""

from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import tifffile
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.schemas.datasets import (
    DatasetDimensions,
    DatasetIntakeResponse,
    DatasetSlot,
    IntensityRange,
)

router = APIRouter(prefix="/v1/datasets", tags=["datasets"])

ALLOWED_EXTENSIONS: dict[DatasetSlot, set[str]] = {
    "ctTiffStack": {".tif", ".tiff"},
    "npyVolume": {".npy"},
    "stlCad": {".stl", ".step", ".stp"},
    "graphJson": {".json", ".graphml"},
}


@router.post("/intake", response_model=DatasetIntakeResponse)
async def intake_dataset(
    slot: DatasetSlot = Form(...),
    files: list[UploadFile] = File(...),
) -> DatasetIntakeResponse:
    """Validate uploaded dataset files and return compact intake metadata."""
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required.")

    file_names = [upload.filename or "unnamed" for upload in files]
    errors = _validate_extensions(slot, file_names)

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

    try:
        if slot == "npyVolume":
            return await _intake_npy(slot, files[0], file_names)
        if slot == "graphJson":
            return await _intake_graph(slot, files[0], file_names)
        if slot == "ctTiffStack":
            return await _intake_tiff_stack(slot, files, file_names)
        return _intake_design_file(slot, file_names)
    finally:
        for upload in files:
            await upload.close()


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


async def _intake_npy(
    slot: DatasetSlot,
    upload: UploadFile,
    file_names: list[str],
) -> DatasetIntakeResponse:
    contents = await upload.read()

    try:
        array = np.load(BytesIO(contents), allow_pickle=False)
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


async def _intake_graph(
    slot: DatasetSlot,
    upload: UploadFile,
    file_names: list[str],
) -> DatasetIntakeResponse:
    suffix = Path(upload.filename or "").suffix.lower()

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

    contents = await upload.read()

    try:
        graph_data = json.loads(contents.decode("utf-8"))
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


async def _intake_tiff_stack(
    slot: DatasetSlot,
    uploads: list[UploadFile],
    file_names: list[str],
) -> DatasetIntakeResponse:
    sorted_uploads = sorted(uploads, key=lambda upload: _natural_sort_key(upload.filename or ""))
    sorted_file_names = [upload.filename or "unnamed" for upload in sorted_uploads]
    stack_depth = 0
    x_dimension: int | None = None
    y_dimension: int | None = None
    intensity_min: float | None = None
    intensity_max: float | None = None
    embedded_metadata: dict[str, Any] = {}
    voxel_size_micron: float | None = None

    for index, upload in enumerate(sorted_uploads):
        contents = await upload.read()

        try:
            with tifffile.TiffFile(BytesIO(contents)) as tiff:
                array = tiff.asarray()
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
            "Voxel size could not be read from TIFF metadata; enter voxel_size_micron manually."
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
    file_names: list[str],
) -> DatasetIntakeResponse:
    return DatasetIntakeResponse(
        valid=True,
        slot=slot,
        file_names=file_names,
        file_type=Path(file_names[0]).suffix.lower().lstrip("."),
        dimensions=None,
        intensity_range=None,
        embedded_metadata=None,
        voxel_size_micron=None,
        warnings=[
            "CAD/STL geometry parsing is not implemented yet; file type was validated only."
        ],
        errors=[],
        demo_mode=True,
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
