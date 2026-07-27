"""Dataset intake schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DatasetSlot = Literal["ctTiffStack", "npyVolume", "stlCad", "graphJson"]


class DatasetDimensions(BaseModel):
    """Voxel or geometry dimensions detected from an uploaded dataset asset."""

    model_config = ConfigDict(extra="forbid")

    x: int | None = None
    y: int | None = None
    z: int | None = None


class IntensityRange(BaseModel):
    """Scalar intensity range for volumetric image data."""

    model_config = ConfigDict(extra="forbid")

    min: float
    max: float


class DatasetIntakeResponse(BaseModel):
    """Compact validation result for one dataset upload slot."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    slot: DatasetSlot
    file_names: list[str]
    file_type: str | None = None
    dimensions: DatasetDimensions | None = None
    intensity_range: IntensityRange | None = None
    embedded_metadata: dict[str, Any] | None = None
    voxel_size_micron: float | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    demo_mode: bool
