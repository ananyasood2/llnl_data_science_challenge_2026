"""HTTP and SSE endpoints for the dataset-scoped lattice copilot."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.copilot.contracts import ChatMessageRequest, StoredViewportContext, ViewportContextCreate
from app.copilot.orchestrator import run_copilot
from app.copilot.repository import analysis_repository
from app.copilot.store import viewport_context_store
from app.core.config import get_settings

router = APIRouter(prefix="/v1/copilot", tags=["copilot"])


@router.post("/viewport-contexts", response_model=StoredViewportContext)
async def create_viewport_context(payload: ViewportContextCreate) -> StoredViewportContext:
    if not analysis_repository.supports(payload.dataset_id):
        raise HTTPException(status_code=404, detail=f"Dataset {payload.dataset_id!r} is unavailable to the copilot.")
    return viewport_context_store.put(
        payload,
        analysis_repository.revision(payload.dataset_id, payload.threshold.value),
    )


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/conversations/{conversation_id}/messages")
async def post_message(conversation_id: str, payload: ChatMessageRequest) -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        yield _sse("ack", {"conversation_id": conversation_id, "context_id": payload.context_id})
        yield _sse("tool_progress", {"state": "running", "context_id": payload.context_id})
        try:
            record = await asyncio.to_thread(run_copilot, payload.message, payload.context_id)
        except HTTPException as exc:
            yield _sse("error", {"status": exc.status_code, "detail": exc.detail})
            return
        except Exception as exc:  # pragma: no cover - defensive streaming boundary
            yield _sse("error", {"status": 502, "detail": f"Copilot analysis failed: {exc}"})
            return
        for result in record["tool_results"]:
            yield _sse("tool_result", result)
        for action in record["viewer_actions"]:
            yield _sse("viewer_action", action)
        yield _sse("answer", {"run_id": record["run_id"], "text": record["answer"], "citations": [result["tool_name"] for result in record["tool_results"]]})
        yield _sse("complete", {"run_id": record["run_id"]})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    if not run_id.startswith("crun_") or "/" in run_id or "\\" in run_id:
        raise HTTPException(status_code=404, detail="Copilot run not found.")
    path = get_settings().copilot_artifact_root / "runs" / f"{run_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Copilot run not found.")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str) -> FileResponse:
    if not artifact_id.startswith("report_") or "/" in artifact_id or "\\" in artifact_id:
        raise HTTPException(status_code=404, detail="Copilot artifact not found.")
    path = get_settings().copilot_artifact_root / f"{artifact_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Copilot artifact not found.")
    return FileResponse(path, media_type="application/json", filename=path.name)

