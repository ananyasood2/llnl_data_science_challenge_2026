"""In-memory, expiring viewport-context registry for local development."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from threading import RLock

from fastapi import HTTPException

from app.core.config import get_settings

from .contracts import StoredViewportContext, ViewportContextCreate


class ViewportContextStore:
    def __init__(self, ttl_minutes: int = 30) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._items: dict[str, StoredViewportContext] = {}
        self._lock = RLock()

    def put(self, payload: ViewportContextCreate, analysis_revision: dict[str, str]) -> StoredViewportContext:
        serialized = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(
            f"{serialized}:{analysis_revision.get('artifact_revision', '')}".encode("utf-8")
        ).hexdigest()
        now = datetime.now(UTC)
        stored = StoredViewportContext(
            **payload.model_dump(),
            context_id=f"vctx_{secrets.token_urlsafe(12)}",
            fingerprint=fingerprint,
            expires_at=now + self._ttl,
            analysis_revision=analysis_revision,
        )
        with self._lock:
            self._items = {key: value for key, value in self._items.items() if value.expires_at > now}
            self._items[stored.context_id] = stored
        self._path(stored.context_id).parent.mkdir(parents=True, exist_ok=True)
        self._path(stored.context_id).write_text(
            stored.model_dump_json(indent=2), encoding="utf-8"
        )
        return stored

    def get(self, context_id: str) -> StoredViewportContext:
        with self._lock:
            value = self._items.get(context_id)
        if value is None:
            path = self._path(context_id)
            if path.is_file():
                try:
                    value = StoredViewportContext.model_validate_json(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    value = None
        if value is None:
            raise HTTPException(status_code=404, detail="Viewport context was not found. Capture the viewport again.")
        if value.expires_at <= datetime.now(UTC):
            raise HTTPException(status_code=409, detail="Viewport context is stale. Capture the viewport again.")
        with self._lock:
            self._items[context_id] = value
        return value

    @staticmethod
    def _path(context_id: str):
        if not context_id.startswith("vctx_") or "/" in context_id or "\\" in context_id:
            raise HTTPException(status_code=404, detail="Viewport context was not found. Capture the viewport again.")
        return get_settings().copilot_artifact_root / "contexts" / f"{context_id}.json"


viewport_context_store = ViewportContextStore()
