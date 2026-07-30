"""HTTP endpoints for the traceable measurement copilot."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.measurement_copilot.contracts import (
    MeasurementChatRequest,
    MeasurementContextCreate,
    MeasurementCopilotResponse,
    StoredMeasurementContext,
)
from app.measurement_copilot.orchestrator import run_measurement_copilot
from app.measurement_copilot.tools import create_measurement_context as create_context_tool


router = APIRouter(prefix="/v1/measurement-copilot", tags=["measurement-copilot"])


@router.post("/contexts", response_model=StoredMeasurementContext)
async def create_measurement_context(
    payload: MeasurementContextCreate,
) -> StoredMeasurementContext:
    return StoredMeasurementContext.model_validate(
        create_context_tool(**payload.model_dump(exclude={"version"}))
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MeasurementCopilotResponse,
)
async def post_measurement_message(
    conversation_id: str,
    payload: MeasurementChatRequest,
) -> MeasurementCopilotResponse:
    if not conversation_id.startswith("mconv_") or "/" in conversation_id or "\\" in conversation_id:
        raise HTTPException(status_code=422, detail="Invalid measurement conversation ID.")
    record = await asyncio.to_thread(
        run_measurement_copilot,
        payload.message,
        payload.context_id,
    )
    return MeasurementCopilotResponse.model_validate(record)


@router.get("/runs/{run_id}", response_model=MeasurementCopilotResponse)
async def get_measurement_run(run_id: str) -> MeasurementCopilotResponse:
    if not run_id.startswith("mrun_") or "/" in run_id or "\\" in run_id:
        raise HTTPException(status_code=404, detail="Measurement run not found.")
    path = get_settings().measurement_artifact_root / "runs" / f"{run_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Measurement run not found.")
    return MeasurementCopilotResponse.model_validate_json(path.read_text(encoding="utf-8"))


@router.get("/artifacts/{artifact_id}")
async def get_measurement_artifact(
    artifact_id: str,
    format: str = Query(default="markdown", pattern="^(markdown|json)$"),
) -> FileResponse:
    if (
        not artifact_id.startswith("measurement_report_")
        or "/" in artifact_id
        or "\\" in artifact_id
    ):
        raise HTTPException(status_code=404, detail="Measurement artifact not found.")
    suffix = ".md" if format == "markdown" else ".json"
    path = get_settings().measurement_artifact_root / "reports" / f"{artifact_id}{suffix}"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Measurement artifact not found.")
    media_type = "text/markdown" if suffix == ".md" else "application/json"
    return FileResponse(path, media_type=media_type, filename=path.name)
