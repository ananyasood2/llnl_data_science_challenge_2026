"""Public contracts for deterministic lattice measurements."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MeasurementSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    analysis_revision: str
    generated_at: datetime
    thickness: dict[str, Any]
    relative_density: dict[str, Any]
    comparison: dict[str, Any]
    warnings: list[str]
    provenance: dict[str, Any]
    thickness_map: dict[str, Any] | None = None


class MeasurementOutlierResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    analysis_revision: str
    cutoff_um: float
    total_below_cutoff: int
    returned_count: int
    truncated: bool
    struts: list[dict[str, Any]]


class CutoffSensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cutoffs_um: list[float] = Field(min_length=1, max_length=20)


class CutoffSensitivityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    analysis_revision: str
    eligible_strut_count: int
    comparison_type: str
    results: list[dict[str, Any]]

