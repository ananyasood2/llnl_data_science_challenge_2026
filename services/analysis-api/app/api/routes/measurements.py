"""FastAPI routes for deterministic measurement evidence."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.repositories.measurements import (
    MeasurementDatasetNotFoundError,
    MeasurementPrerequisiteError,
    MeasurementStrutNotFoundError,
    measurement_repository,
)
from app.schemas.measurements import (
    CutoffSensitivityRequest,
    CutoffSensitivityResponse,
    MeasurementOutlierResponse,
    MeasurementSummaryResponse,
    SelectedStrutMeasurementResponse,
)


router = APIRouter(prefix="/v1/datasets", tags=["measurements"])


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (MeasurementDatasetNotFoundError, MeasurementStrutNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, MeasurementPrerequisiteError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="Measurement analysis failed.")


@router.get("/{dataset_id}/measurements", response_model=MeasurementSummaryResponse)
async def get_measurements(
    dataset_id: str,
    target_thickness_um: float = Query(default=350.0, gt=0),
    critical_cutoff_um: float = Query(default=300.0, gt=0),
    user_cutoff_um: float = Query(default=350.0, gt=0),
    target_density_percent: float = Query(default=10.0, gt=0, le=100),
    include_map: bool = Query(default=False),
) -> MeasurementSummaryResponse:
    try:
        result = measurement_repository.summary(
            dataset_id,
            target_thickness_um=target_thickness_um,
            critical_cutoff_um=critical_cutoff_um,
            user_cutoff_um=user_cutoff_um,
            target_density_percent=target_density_percent,
            include_map=include_map,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    return MeasurementSummaryResponse.model_validate(result)


@router.get(
    "/{dataset_id}/measurements/outliers",
    response_model=MeasurementOutlierResponse,
)
async def get_measurement_outliers(
    dataset_id: str,
    cutoff_um: float = Query(default=350.0, gt=0),
    limit: int = Query(default=25, ge=1, le=200),
) -> MeasurementOutlierResponse:
    try:
        result = measurement_repository.outliers(
            dataset_id,
            cutoff_um=cutoff_um,
            limit=limit,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    return MeasurementOutlierResponse.model_validate(result)


@router.post(
    "/{dataset_id}/measurements/cutoff-sensitivity",
    response_model=CutoffSensitivityResponse,
)
async def get_cutoff_sensitivity(
    dataset_id: str,
    payload: CutoffSensitivityRequest,
) -> CutoffSensitivityResponse:
    try:
        result = measurement_repository.sensitivity(
            dataset_id,
            cutoffs_um=payload.cutoffs_um,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    return CutoffSensitivityResponse.model_validate(result)


@router.get(
    "/{dataset_id}/measurements/struts/{strut_id}",
    response_model=SelectedStrutMeasurementResponse,
)
async def get_selected_strut_measurement(
    dataset_id: str,
    strut_id: str,
    expected_analysis_revision: str = Query(min_length=1, max_length=256),
    target_thickness_um: float = Query(gt=0, le=2_000),
    critical_cutoff_um: float = Query(gt=0, le=2_000),
    user_cutoff_um: float = Query(gt=0, le=2_000),
    neighbor_limit: int = Query(default=25, ge=1, le=50),
) -> SelectedStrutMeasurementResponse:
    try:
        result = measurement_repository.strut_detail(
            dataset_id,
            strut_id,
            expected_analysis_revision=expected_analysis_revision,
            target_thickness_um=target_thickness_um,
            critical_cutoff_um=critical_cutoff_um,
            user_cutoff_um=user_cutoff_um,
            neighbor_limit=neighbor_limit,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
    return SelectedStrutMeasurementResponse.model_validate(result)
