"""Compact, browser-safe contracts for the Part 2 inspection dashboard."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CandidateFlag = Literal["missing_candidate", "disconnected_candidate", "uncertain_candidate", "clear"]


class InspectionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    pipeline: str
    volume_shape_zyx: tuple[int, int, int]
    selected_threshold: int
    counts: dict[CandidateFlag, int]
    limitation: str
    diagnostics_url: str


class StrutCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strut_id: int
    material_fraction: float = Field(ge=0, le=1)
    longest_gap_samples: int = Field(ge=0)
    flag: CandidateFlag
    x_voxel: float
    y_voxel: float
    z_voxel: float


class CandidatePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    items: list[StrutCandidate]
