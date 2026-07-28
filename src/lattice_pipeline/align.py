"""Axis-aligned transforms between design coordinates and CT voxel space."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.spatial import cKDTree


def _xyz_array(value: Any, *, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=float)
    if result.shape[-1:] != (3,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must have a final dimension of three finite xyz values")
    return result


@dataclass(frozen=True)
class AlignmentTransform:
    """Per-axis affine transform ``voxel_xyz = design_xyz * scale + offset``."""

    scale: tuple[float, float, float]
    offset: tuple[float, float, float]
    source: str

    def __post_init__(self) -> None:
        scale = _xyz_array(self.scale, name="scale")
        _xyz_array(self.offset, name="offset")
        if np.any(scale == 0):
            raise ValueError("Alignment scale values must be non-zero")

    def apply(self, points_xyz: Any) -> np.ndarray:
        points = _xyz_array(points_xyz, name="points_xyz")
        return points * np.asarray(self.scale) + np.asarray(self.offset)

    def inverse(self, voxel_points_xyz: Any) -> np.ndarray:
        points = _xyz_array(voxel_points_xyz, name="voxel_points_xyz")
        return (points - np.asarray(self.offset)) / np.asarray(self.scale)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "scale": list(self.scale),
            "offset": list(self.offset),
            "source": self.source,
            "coordinate_order": "xyz",
            "equation": "voxel_xyz = design_xyz * scale + offset",
        }


def identity_alignment(*, source: str = "registered_json") -> AlignmentTransform:
    """Return the passthrough used by a graph already registered in voxel xyz."""
    return AlignmentTransform(
        scale=(1.0, 1.0, 1.0),
        offset=(0.0, 0.0, 0.0),
        source=source,
    )


def _bbox_min_max(
    bbox_xyz: Mapping[str, Sequence[float]] | Sequence[Sequence[float]],
) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(bbox_xyz, Mapping):
        minimum = bbox_xyz.get("min_xyz")
        maximum = bbox_xyz.get("max_xyz")
    else:
        values = np.asarray(bbox_xyz, dtype=float)
        if values.shape != (2, 3):
            raise ValueError("bbox_xyz must be [[min_x,min_y,min_z], [max_x,max_y,max_z]]")
        minimum, maximum = values
    if minimum is None or maximum is None:
        raise ValueError("bbox_xyz mapping needs min_xyz and max_xyz")
    minimum = _xyz_array(minimum, name="bbox min")
    maximum = _xyz_array(maximum, name="bbox max")
    if np.any(maximum <= minimum):
        raise ValueError(f"Degenerate bbox: min={minimum}, max={maximum}")
    return minimum, maximum


def mask_bbox_xyz(mask: np.ndarray) -> dict[str, list[float]]:
    """Return the inclusive foreground bounding box in public xyz order."""
    if mask.ndim != 3:
        raise ValueError(f"Expected a 3D mask in zyx array order, got {mask.shape}")
    locations_zyx = np.argwhere(mask)
    if not locations_zyx.size:
        raise ValueError("Cannot align against an empty segmentation mask")
    minimum_xyz = locations_zyx.min(axis=0)[::-1].astype(float)
    maximum_xyz = locations_zyx.max(axis=0)[::-1].astype(float)
    return {"min_xyz": minimum_xyz.tolist(), "max_xyz": maximum_xyz.tolist()}


def bbox_match_alignment(
    design_positions_xyz: Any,
    scan_bbox_xyz: Mapping[str, Sequence[float]] | Sequence[Sequence[float]],
) -> AlignmentTransform:
    """Match design and foreground bounding boxes independently on each axis."""
    positions = _xyz_array(design_positions_xyz, name="design_positions_xyz")
    if positions.ndim != 2 or positions.shape[0] < 2:
        raise ValueError("At least two design positions are required for bbox matching")
    design_min = positions.min(axis=0)
    design_max = positions.max(axis=0)
    design_extent = design_max - design_min
    if np.any(design_extent <= 0):
        raise ValueError(
            "Design graph has a degenerate axis and cannot be bbox-aligned: "
            f"extent={design_extent.tolist()}"
        )
    scan_min, scan_max = _bbox_min_max(scan_bbox_xyz)
    scale = (scan_max - scan_min) / design_extent
    offset = scan_min - design_min * scale
    return AlignmentTransform(
        scale=tuple(float(v) for v in scale),
        offset=tuple(float(v) for v in offset),
        source="bbox_match",
    )


def positions_fit_volume(
    positions_xyz: Any,
    volume_shape_zyx: Sequence[int],
    *,
    margin_voxels: float = 1.0,
) -> bool:
    """Whether xyz points plausibly occupy the supplied zyx voxel volume."""
    positions = _xyz_array(positions_xyz, name="positions_xyz")
    shape = np.asarray(volume_shape_zyx, dtype=float)
    if shape.shape != (3,) or np.any(shape <= 0):
        raise ValueError(f"Invalid volume shape {volume_shape_zyx}")
    upper_xyz = shape[::-1] - 1 + margin_voxels
    return bool(
        np.all(positions >= -margin_voxels) and np.all(positions <= upper_xyz)
    )


def is_registered_design(
    graph: Mapping[str, Any],
    volume_shape_zyx: Sequence[int] | None = None,
) -> bool:
    """Detect the challenge's registered JSONs without assuming identity blindly."""
    path = Path(str(graph.get("path", "")))
    path_hint = path.parent.name.lower() == "registered_jsons"
    explicit = graph.get("raw_metadata", {}).get("coordinate_system")
    explicit_hint = isinstance(explicit, str) and "voxel" in explicit.lower()
    if not (path_hint or explicit_hint):
        return False
    if volume_shape_zyx is None:
        return True
    return positions_fit_volume(graph["positions_xyz"], volume_shape_zyx)


def resolve_alignment(
    graph: Mapping[str, Any],
    *,
    volume_shape_zyx: Sequence[int] | None = None,
    scan_bbox_xyz: (
        Mapping[str, Sequence[float]] | Sequence[Sequence[float]] | None
    ) = None,
    registered: bool | None = None,
) -> AlignmentTransform:
    """Choose registered passthrough or the documented bbox-match fallback.

    Auto-detection only accepts identity when the path/metadata says registered
    *and* graph coordinates fit within the supplied volume. Callers may force
    either behavior with ``registered=True`` or ``False``.
    """
    if registered is None:
        registered = is_registered_design(graph, volume_shape_zyx)
    if registered:
        if volume_shape_zyx is not None and not positions_fit_volume(
            graph["positions_xyz"], volume_shape_zyx
        ):
            raise ValueError(
                "Graph was marked registered, but its xyz positions do not fit "
                f"volume shape zyx={tuple(volume_shape_zyx)}"
            )
        return identity_alignment()
    if scan_bbox_xyz is None:
        raise ValueError(
            "scan_bbox_xyz is required for a design graph that is not already registered"
        )
    return bbox_match_alignment(graph["positions_xyz"], scan_bbox_xyz)


def refine_positions_to_skeleton(
    positions_xyz: Any,
    edge_indices: Any,
    skeleton: np.ndarray,
    *,
    iterations: int = 12,
    keep_fraction: float = 0.80,
    max_correspondence_vox: float = 5.0,
    damping: float = 0.5,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Robustly refine an already-close graph registration to a CT skeleton.

    Four interior samples from every design edge are matched to their nearest
    skeleton voxels.  At each iteration only the closest correspondence
    fraction is retained, which prevents real missing struts and scan debris
    from steering the fit.  The small damped affine updates correct residual
    scale, shear, rotation, and translation left by the supplied registration.
    """

    positions = _xyz_array(positions_xyz, name="positions_xyz")
    edges = np.asarray(edge_indices, dtype=np.int64)
    skel = np.asarray(skeleton, dtype=bool)
    if positions.ndim != 2 or len(positions) < 4:
        raise ValueError("positions_xyz must contain at least four points")
    if edges.ndim != 2 or edges.shape[1] != 2 or len(edges) == 0:
        raise ValueError("edge_indices must be a non-empty [n, 2] array")
    if np.any(edges < 0) or np.any(edges >= len(positions)):
        raise ValueError("edge_indices contains an out-of-range node index")
    if skel.ndim != 3:
        raise ValueError(f"Expected a 3-D skeleton, got shape {skel.shape!r}")
    if not 0.5 <= keep_fraction < 1:
        raise ValueError("keep_fraction must be in [0.5, 1)")
    if iterations < 1 or max_correspondence_vox <= 0 or not 0 < damping <= 1:
        raise ValueError("Invalid refinement iteration, distance, or damping value")

    skeleton_zyx = np.argwhere(skel)
    if len(skeleton_zyx) < 4:
        return positions.copy(), {
            "applied": False,
            "reason": "too_few_skeleton_voxels",
        }

    skeleton_xyz = skeleton_zyx[:, ::-1].astype(float, copy=False)
    tree = cKDTree(skeleton_xyz)
    fractions = np.asarray([0.2, 0.4, 0.6, 0.8], dtype=float)
    samples = (
        positions[edges[:, 0], None, :] * (1 - fractions)[None, :, None]
        + positions[edges[:, 1], None, :] * fractions[None, :, None]
    ).reshape(-1, 3)
    refined = positions.copy()
    initial_distances = tree.query(samples, workers=-1)[0]
    completed = 0

    for iteration in range(iterations):
        distances, nearest = tree.query(samples, workers=-1)
        cutoff = min(
            float(max_correspondence_vox),
            float(np.quantile(distances, keep_fraction)),
        )
        keep = distances <= cutoff
        if np.count_nonzero(keep) < 16:
            break

        source = np.column_stack(
            [samples[keep], np.ones(np.count_nonzero(keep))]
        )
        target = skeleton_xyz[nearest[keep]]
        coefficients = np.linalg.lstsq(source, target, rcond=None)[0]
        linear = np.eye(3) + damping * (coefficients[:3] - np.eye(3))
        offset = damping * coefficients[3]
        samples = samples @ linear + offset
        refined = refined @ linear + offset
        completed = iteration + 1

        update_size = max(
            float(np.max(np.abs(linear - np.eye(3)))),
            float(np.max(np.abs(offset))),
        )
        if update_size < 1e-4:
            break

    final_distances = tree.query(samples, workers=-1)[0]
    transform = np.linalg.lstsq(
        np.column_stack([positions, np.ones(len(positions))]),
        refined,
        rcond=None,
    )[0]
    return refined, {
        "applied": bool(completed),
        "iterations": completed,
        "sample_count": int(len(samples)),
        "keep_fraction": float(keep_fraction),
        "median_distance_before_vox": float(np.median(initial_distances)),
        "median_distance_after_vox": float(np.median(final_distances)),
        "p90_distance_before_vox": float(np.quantile(initial_distances, 0.9)),
        "p90_distance_after_vox": float(np.quantile(final_distances, 0.9)),
        "affine_homogeneous_rows": transform.tolist(),
    }
