"""Read-only access to qualified measurement artifacts."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, Sequence

import numpy as np

from lattice_pipeline.measurements import (
    build_thickness_map,
    compare_measurements_to_policy,
    compute_cutoff_sensitivity,
    compute_relative_density,
    compute_thickness_summary,
    list_out_of_spec_struts,
)

from app.core.config import get_settings


DATASET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class MeasurementDatasetNotFoundError(FileNotFoundError):
    """Raised when a dataset ID is not present in the configured catalog."""


class MeasurementPrerequisiteError(RuntimeError):
    """Raised when registered scientific artifacts are not qualified yet."""


@lru_cache(maxsize=8)
def _read_analysis(path_text: str, modified_ns: int) -> dict[str, Any]:
    del modified_ns
    return json.loads(Path(path_text).read_text(encoding="utf-8"))


class MeasurementRepository:
    """Build measurement results from immutable registered analysis artifacts."""

    def __init__(self) -> None:
        self._summary_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._cache_lock = RLock()

    @staticmethod
    def _validate_dataset_id(dataset_id: str) -> None:
        if not DATASET_ID_PATTERN.fullmatch(dataset_id):
            raise MeasurementDatasetNotFoundError("Measurement dataset was not found.")

    def _dataset_dir(self, dataset_id: str) -> Path:
        self._validate_dataset_id(dataset_id)
        root = get_settings().builtin_data_root.resolve()
        dataset_dir = (root / dataset_id).resolve()
        if dataset_dir.parent != root or not dataset_dir.is_dir():
            raise MeasurementDatasetNotFoundError(
                f"Dataset {dataset_id!r} is not available for measurement analysis."
            )
        return dataset_dir

    def _paths(self, dataset_id: str) -> tuple[Path, Path]:
        dataset_dir = self._dataset_dir(dataset_id)
        processed = dataset_dir / "processed"
        analysis_path = processed / "analysis.json"
        mask_path = processed / "mask.npy"
        if not analysis_path.is_file() or not mask_path.is_file():
            raise MeasurementPrerequisiteError(
                "Registered analysis and segmentation artifacts are required before "
                "measurement analysis can run."
            )
        return analysis_path, mask_path

    def analysis(self, dataset_id: str) -> dict[str, Any]:
        analysis_path, _ = self._paths(dataset_id)
        analysis = _read_analysis(str(analysis_path), analysis_path.stat().st_mtime_ns)
        meta = analysis.get("meta", {})
        if not meta.get("cache_fingerprint") or not analysis.get("struts"):
            raise MeasurementPrerequisiteError(
                "The analysis artifact does not contain a registered revision and strut measurements."
            )
        voxel_size = meta.get("voxel_size_mm")
        if voxel_size is None or float(voxel_size) <= 0:
            raise MeasurementPrerequisiteError(
                "A qualified physical voxel spacing is required before reporting microns or density."
            )
        return analysis

    def revision(self, dataset_id: str) -> str:
        return str(self.analysis(dataset_id)["meta"]["cache_fingerprint"])

    @staticmethod
    def _registered_roi(
        analysis: dict[str, Any],
        mask: np.ndarray,
        target_thickness_um: float,
    ) -> tuple[tuple[slice, slice, slice], dict[str, list[float]]]:
        meta = analysis["meta"]
        stride = int(meta.get("analysis_stride", 1))
        voxel_size_mm = float(meta["voxel_size_mm"])
        points = np.asarray(
            [point for strut in analysis["struts"] for point in strut.get("polyline", [])],
            dtype=float,
        )
        if points.ndim != 2 or points.shape[1:] != (3,) or not np.all(np.isfinite(points)):
            raise MeasurementPrerequisiteError(
                "Registered XYZ strut geometry is required for the relative-density ROI."
            )
        target_radius_vox = (float(target_thickness_um) / 2000.0) / voxel_size_mm
        lower_xyz = np.floor((points.min(axis=0) - target_radius_vox) / stride).astype(int)
        upper_xyz = np.ceil((points.max(axis=0) + target_radius_vox) / stride).astype(int) + 1
        shape_xyz = np.asarray(mask.shape[::-1], dtype=int)
        lower_xyz = np.clip(lower_xyz, 0, shape_xyz)
        upper_xyz = np.clip(upper_xyz, 0, shape_xyz)
        if np.any(upper_xyz <= lower_xyz):
            raise MeasurementPrerequisiteError("The registered design ROI does not intersect the mask.")
        slices_zyx = (
            slice(int(lower_xyz[2]), int(upper_xyz[2])),
            slice(int(lower_xyz[1]), int(upper_xyz[1])),
            slice(int(lower_xyz[0]), int(upper_xyz[0])),
        )
        bounds = {
            "min_xyz": [float(value * stride) for value in lower_xyz],
            "max_xyz": [float(value * stride) for value in upper_xyz],
        }
        return slices_zyx, bounds

    def _relative_density(
        self,
        dataset_id: str,
        analysis: dict[str, Any],
        *,
        target_thickness_um: float,
        target_density_percent: float,
    ) -> dict[str, Any]:
        _, mask_path = self._paths(dataset_id)
        mask = np.load(mask_path, mmap_mode="r", allow_pickle=False)
        slices_zyx, bounds = self._registered_roi(
            analysis,
            mask,
            target_thickness_um,
        )
        roi = mask[slices_zyx]
        foreground_count = int(np.count_nonzero(roi))
        enclosing_count = int(roi.size)
        effective_voxel_size = (
            float(analysis["meta"]["voxel_size_mm"])
            * int(analysis["meta"].get("analysis_stride", 1))
        )
        return compute_relative_density(
            segmented_voxel_count=foreground_count,
            enclosing_voxel_count=enclosing_count,
            effective_voxel_size_mm=effective_voxel_size,
            target_percent=target_density_percent,
            roi_definition="registered_graph_aabb_expanded_by_target_radius",
            roi_bounds_xyz=bounds,
        )

    @staticmethod
    def _warnings(analysis: dict[str, Any]) -> list[str]:
        meta = analysis["meta"]
        warnings = [
            "Pass/warn/fail uses demo-policy-v1 and is not a scientist-approved acceptance decision.",
            "Relative density is sensitive to segmentation threshold and registered ROI definition.",
        ]
        source = str(meta.get("voxel_size_source", ""))
        tiff_metadata = meta.get("tiff_metadata") or {}
        if "estimated" in source or (
            tiff_metadata and tiff_metadata.get("voxel_size_mm") is None
        ):
            warnings.append(
                "Source TIFF spacing is unavailable; the workflow-supplied physical spacing must be verified against the design span."
            )
        if meta.get("unreliable_boundary_faces"):
            warnings.append(
                "The registered analysis flags at least one unreliable scan boundary; review boundary struts separately."
            )
        return warnings

    def summary(
        self,
        dataset_id: str,
        *,
        target_thickness_um: float = 350.0,
        critical_cutoff_um: float = 300.0,
        user_cutoff_um: float = 350.0,
        target_density_percent: float = 10.0,
        include_map: bool = False,
    ) -> dict[str, Any]:
        analysis = self.analysis(dataset_id)
        meta = analysis["meta"]
        cache_key = (
            str(get_settings().builtin_data_root.resolve()),
            dataset_id,
            str(meta["cache_fingerprint"]),
            round(float(target_thickness_um), 6),
            round(float(critical_cutoff_um), 6),
            round(float(user_cutoff_um), 6),
            round(float(target_density_percent), 6),
            include_map,
        )
        with self._cache_lock:
            cached = self._summary_cache.get(cache_key)
        if cached is not None:
            return cached
        thickness = compute_thickness_summary(
            analysis["struts"],
            target_um=target_thickness_um,
            critical_cutoff_um=critical_cutoff_um,
            user_cutoff_um=user_cutoff_um,
        )
        density = self._relative_density(
            dataset_id,
            analysis,
            target_thickness_um=target_thickness_um,
            target_density_percent=target_density_percent,
        )
        comparison = compare_measurements_to_policy(thickness, density)
        result: dict[str, Any] = {
            "dataset_id": dataset_id,
            "analysis_revision": str(meta["cache_fingerprint"]),
            "generated_at": datetime.now(UTC).isoformat(),
            "thickness": thickness,
            "relative_density": density,
            "comparison": comparison,
            "warnings": self._warnings(analysis),
            "provenance": {
                "analysis_version": meta.get("analysis_version"),
                "analysis_stride": meta.get("analysis_stride"),
                "voxel_size_mm": meta.get("voxel_size_mm"),
                "voxel_size_source": meta.get("voxel_size_source"),
                "segmentation_threshold": meta.get("threshold"),
                "threshold_source": meta.get("threshold_source"),
                "coordinate_space": "registered_voxel_xyz",
            },
            "thickness_map": None,
        }
        if include_map:
            result["thickness_map"] = build_thickness_map(analysis["struts"])
        with self._cache_lock:
            self._summary_cache[cache_key] = result
            while len(self._summary_cache) > 16:
                self._summary_cache.pop(next(iter(self._summary_cache)))
        return result

    def outliers(
        self,
        dataset_id: str,
        *,
        cutoff_um: float,
        limit: int = 25,
    ) -> dict[str, Any]:
        analysis = self.analysis(dataset_id)
        return {
            "dataset_id": dataset_id,
            "analysis_revision": self.revision(dataset_id),
            **list_out_of_spec_struts(
                analysis["struts"],
                cutoff_um=cutoff_um,
                limit=limit,
            ),
        }

    def sensitivity(
        self,
        dataset_id: str,
        *,
        cutoffs_um: Sequence[float],
    ) -> dict[str, Any]:
        analysis = self.analysis(dataset_id)
        return {
            "dataset_id": dataset_id,
            "analysis_revision": self.revision(dataset_id),
            **compute_cutoff_sensitivity(analysis["struts"], cutoffs_um),
        }


measurement_repository = MeasurementRepository()
