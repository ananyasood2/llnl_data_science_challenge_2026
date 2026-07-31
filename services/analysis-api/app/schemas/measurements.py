"""Public contracts for deterministic lattice measurements."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


class StrutPercentile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank_percent: float | None
    count_at_or_below: int | None
    population_count: int
    method: Literal["weak_ecdf_lte"]


class StrutTargetComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_um: float
    difference_um: float | None
    below: bool | None


class StrutCutoffComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cutoff_um: float
    difference_um: float | None
    below: bool | None


class SelectedStrutMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strut_id: int | str
    analysis_status: str | None
    measurement_eligible: bool
    measured_thickness_um: float | None
    design_thickness_um: float | None
    thickness_ratio: float | None
    endpoint_node_ids: list[int | str] = Field(max_length=2)
    percentile: StrutPercentile
    target_comparison: StrutTargetComparison
    critical_cutoff_comparison: StrutCutoffComparison
    user_cutoff_comparison: StrutCutoffComparison


class NeighborStrutMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strut_id: int | str
    analysis_status: str | None
    measured_thickness_um: float | None
    shared_node_ids: list[int | str] = Field(min_length=1, max_length=2)


class SelectedStrutNeighbors(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: Literal["other_registered_struts_sharing_an_endpoint_node"]
    total_count: int
    eligible_count: int
    excluded_count: int
    median_thickness_um: float | None
    selected_minus_median_um: float | None
    returned_count: int
    truncated: bool
    struts: list[NeighborStrutMeasurement] = Field(max_length=50)


class SelectedStrutMeasurementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    analysis_revision: str
    unit: Literal["um"]
    method: Literal["skeleton_edt_median_diameter"]
    method_version: Literal["1"]
    eligibility_rule: Literal["finite positive measured_thickness_um"]
    eligible_strut_count: int
    excluded_strut_count: int
    strut: SelectedStrutMeasurement
    neighbors: SelectedStrutNeighbors
    warnings: list[str]
    provenance: dict[str, Any]
