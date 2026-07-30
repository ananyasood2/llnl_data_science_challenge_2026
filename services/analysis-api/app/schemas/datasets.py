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


class GeometryBounds(BaseModel):
    """Axis-aligned coordinate bounds for uploaded design geometry."""

    model_config = ConfigDict(extra="forbid")

    x: tuple[float, float]
    y: tuple[float, float]
    z: tuple[float, float]


class GeometryMetadata(BaseModel):
    """Compact geometry metadata extracted from an uploaded design reference."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["stl-ascii", "stl-binary"]
    triangle_count: int
    vertex_count: int
    dimensions: dict[Literal["x", "y", "z"], float]
    bounds: GeometryBounds


class DatasetIntakeResponse(BaseModel):
    """Compact validation result for one dataset upload slot."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    dataset_id: str | None = None
    slot: DatasetSlot
    file_names: list[str]
    generated_file_names: list[str] = Field(default_factory=list)
    graph_reference_available: bool = False
    graph_reference_file_name: str | None = None
    file_type: str | None = None
    dimensions: DatasetDimensions | None = None
    intensity_range: IntensityRange | None = None
    geometry_metadata: GeometryMetadata | None = None
    embedded_metadata: dict[str, Any] | None = None
    voxel_size_micron: float | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    demo_mode: bool
