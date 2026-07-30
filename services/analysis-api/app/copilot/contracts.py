"""Versioned, browser-safe contracts for the lattice copilot."""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Vec3(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    z: float


class BoundsXYZ(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_xyz: list[float] = Field(min_length=3, max_length=3)
    max_xyz: list[float] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def valid_bounds(self) -> "BoundsXYZ":
        values = [*self.min_xyz, *self.max_xyz]
        if any(not math.isfinite(value) for value in values):
            raise ValueError("bounds must contain finite values")
        if any(low > high for low, high in zip(self.min_xyz, self.max_xyz)):
            raise ValueError("each minimum bound must be less than or equal to its maximum")
        return self


class CameraState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eye: Vec3
    center: Vec3 = Field(default_factory=lambda: Vec3(x=0, y=0, z=0))
    up: Vec3 = Field(default_factory=lambda: Vec3(x=0, y=0, z=1))
    projection: Literal["perspective", "orthographic"] = "perspective"


class ThresholdState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | None = None
    unit: str = "normalized_intensity"
    source: Literal["automatic", "manual"] = "automatic"


class SelectedElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["strut", "node"]
    id: int | str


class ViewportContextCreate(BaseModel):
    """The only scientific scope accepted from a browser client."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    captured_at: datetime
    dataset_id: str = Field(min_length=1, max_length=128)
    threshold: ThresholdState = Field(default_factory=ThresholdState)
    coordinate_space: Literal["registered_voxel_xyz"] = "registered_voxel_xyz"
    region: BoundsXYZ
    camera: CameraState
    visible_statuses: list[str] = Field(default_factory=list, max_length=8)
    visible_element_types: list[Literal["strut", "node"]] = Field(default_factory=list, max_length=2)
    selected_element: SelectedElement | None = None
    viewer_revision: int = Field(ge=0)

    @field_validator("visible_statuses")
    @classmethod
    def valid_statuses(cls, values: list[str]) -> list[str]:
        allowed = {"healthy", "missing", "thin", "thick", "broken", "disconnected", "uncertain"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unknown status filters: {sorted(unknown)}")
        return list(dict.fromkeys(values))


class StoredViewportContext(ViewportContextCreate):
    model_config = ConfigDict(extra="forbid")

    context_id: str
    fingerprint: str
    expires_at: datetime
    analysis_revision: dict[str, str]


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4_000)
    context_id: str = Field(min_length=1, max_length=128)


class ToolEnvelope(BaseModel):
    """Compact tool output that can safely be sent to a language model."""

    model_config = ConfigDict(extra="forbid")

    tool_version: Literal["1"] = "1"
    tool_name: str
    context_id: str
    dataset_id: str
    analysis_revision: str
    scope: dict[str, Any]
    summary: dict[str, Any]
    elements: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any]
