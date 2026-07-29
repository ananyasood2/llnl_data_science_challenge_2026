"""Contracts for the generic classification-metrics endpoint."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Average = Literal["binary", "macro", "weighted"]


class MetricsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    y_true: list[str | int] = Field(min_length=1)
    y_pred: list[str | int] = Field(min_length=1)
    average: Average = "binary"
    positive_label: str | int | None = None
    labels: list[str | int] | None = None


class ClassMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    precision: float
    recall: float
    f1: float
    support: int


class MetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accuracy: float
    precision: float
    recall: float
    f1: float
    support: int
    average: Average
    per_class: dict[str, ClassMetrics]
