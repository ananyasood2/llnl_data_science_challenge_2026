"""Read-only access to registered analysis artifacts used by copilot tools."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any

from lattice_pipeline.cache import ensure_analysis
from lattice_pipeline.datasets import DATASETS, get_dataset


class AnalysisRepository:
    """Loads only bundled, registered datasets; raw volumes never leave this layer."""

    def supports(self, dataset_id: str) -> bool:
        return dataset_id in DATASETS

    @lru_cache(maxsize=8)
    def get_analysis(self, dataset_id: str, threshold: float | None) -> dict[str, Any]:
        if not self.supports(dataset_id):
            raise KeyError(dataset_id)
        config = get_dataset(dataset_id)
        return ensure_analysis(
            dataset_id,
            config,
            threshold=threshold,
            voxel_size_mm=float(config["voxel_size_mm"]),
        )

    def revision(self, dataset_id: str, threshold: float | None) -> dict[str, str]:
        """Create a cheap immutable scope key without loading the CT volume."""
        config = get_dataset(dataset_id)
        signature = {
            "dataset_id": dataset_id,
            "threshold": threshold,
            "volume": {"size": config["volume"].stat().st_size, "mtime": config["volume"].stat().st_mtime_ns},
            "design": {"size": config["design"].stat().st_size, "mtime": config["design"].stat().st_mtime_ns},
        }
        fingerprint = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
        return {"graph_hash": fingerprint, "artifact_revision": fingerprint}


analysis_repository = AnalysisRepository()
