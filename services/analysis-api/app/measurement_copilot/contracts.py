"""Versioned public contracts for measurement-agent runs."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MeasurementContextCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["1"] = "1"
    dataset_id: str = Field(min_length=1, max_length=128)
    target_thickness_um: float = Field(default=350.0, gt=0, le=2_000)
    critical_cutoff_um: float = Field(default=300.0, gt=0, le=2_000)
    user_cutoff_um: float = Field(default=350.0, gt=0, le=2_000)
    target_density_percent: float = Field(default=10.0, gt=0, le=100)
    selected_strut_id: int | str | None = None
    visible_statuses: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("target_thickness_um", "critical_cutoff_um", "user_cutoff_um", "target_density_percent")
    @classmethod
    def finite_number(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("measurement context values must be finite")
        return value


class StoredMeasurementContext(MeasurementContextCreate):
    model_config = ConfigDict(extra="forbid")

    context_id: str
    fingerprint: str
    analysis_revision: str
    captured_at: datetime
    expires_at: datetime


class MeasurementChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4_000)


class MeasurementToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_version: Literal["1"] = "1"
    tool_run_id: str
    tool_name: str
    specialist: Literal["Measurement Orchestrator", "Thickness Analysis Agent", "Relative Density Agent"]
    context_id: str
    dataset_id: str
    analysis_revision: str
    scope: dict[str, Any]
    summary: dict[str, Any]
    elements: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any]


class MeasurementCopilotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    context_id: str
    dataset_id: str
    analysis_revision: str
    created_at: datetime
    mode: Literal["openai-tool-calling", "deterministic-local-orchestrator"]
    model: str
    answer: str
    tool_results: list[MeasurementToolEnvelope]
    viewer_actions: list[dict[str, Any]]
    warnings: list[str]

