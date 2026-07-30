"""Short-lived immutable context storage for measurement conversations."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from threading import RLock

from fastapi import HTTPException

from app.core.config import get_settings

from .contracts import MeasurementContextCreate, StoredMeasurementContext


class MeasurementContextStore:
    def __init__(self, ttl_minutes: int = 60) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._items: dict[str, StoredMeasurementContext] = {}
        self._lock = RLock()

    @staticmethod
    def _path(context_id: str):
        if not context_id.startswith("mctx_") or "/" in context_id or "\\" in context_id:
            raise HTTPException(status_code=404, detail="Measurement context was not found.")
        return get_settings().measurement_artifact_root / "contexts" / f"{context_id}.json"

    def put(self, payload: MeasurementContextCreate, revision: str) -> StoredMeasurementContext:
        canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(f"{canonical}:{revision}".encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        stored = StoredMeasurementContext(
            **payload.model_dump(),
            context_id=f"mctx_{secrets.token_urlsafe(12)}",
            fingerprint=fingerprint,
            analysis_revision=revision,
            captured_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._items = {
                key: value for key, value in self._items.items() if value.expires_at > now
            }
            self._items[stored.context_id] = stored
        path = self._path(stored.context_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stored.model_dump_json(indent=2), encoding="utf-8")
        return stored

    def get(self, context_id: str) -> StoredMeasurementContext:
        with self._lock:
            stored = self._items.get(context_id)
        if stored is None:
            path = self._path(context_id)
            if path.is_file():
                try:
                    stored = StoredMeasurementContext.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                except (OSError, ValueError):
                    stored = None
        if stored is None:
            raise HTTPException(
                status_code=404,
                detail="Measurement context was not found. Refresh the measurement page.",
            )
        if stored.expires_at <= datetime.now(UTC):
            raise HTTPException(
                status_code=409,
                detail="Measurement context is stale. Refresh the measurement page.",
            )
        with self._lock:
            self._items[context_id] = stored
        return stored


measurement_context_store = MeasurementContextStore()

