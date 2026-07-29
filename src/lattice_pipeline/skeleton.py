"""Skeletonization, 26-connected topology metrics, and branch extraction."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize

FULL_CONNECTIVITY = np.ones((3, 3, 3), dtype=np.uint8)
NEIGHBORHOOD = FULL_CONNECTIVITY.copy()
NEIGHBORHOOD[1, 1, 1] = 0


def _as_bool_3d(array: np.ndarray, name: str) -> np.ndarray:
    result = np.asanyarray(array)
    if result.ndim != 3:
        raise ValueError(f"Expected a 3-D {name}, got shape {result.shape!r}")
    return np.asarray(result, dtype=bool)


def skeletonize_mask(mask: np.ndarray) -> np.ndarray:
    """Reduce a 3-D material mask to a one-voxel-wide boolean centerline."""

    return np.asarray(skeletonize(_as_bool_3d(mask, "mask")), dtype=bool)


# More explicit synonym for callers that deal with several volume products.
skeletonize_volume = skeletonize_mask


def label_skeleton_components(skeleton: np.ndarray) -> tuple[np.ndarray, int]:
    """Label skeleton components using deliberate full 26-connectivity.

    Face-only (6-connected) labeling incorrectly separates diagonal centerline
    steps in a 3-D skeleton, producing thousands of artificial fragments.
    """

    skel = _as_bool_3d(skeleton, "skeleton")
    labels, count = ndimage.label(skel, structure=FULL_CONNECTIVITY)
    return labels, int(count)


def skeleton_neighbor_counts(skeleton: np.ndarray) -> np.ndarray:
    """Return the number of 26-neighbor skeleton voxels at each voxel."""

    skel = _as_bool_3d(skeleton, "skeleton")
    # uint8 is sufficient for the maximum count of 26.
    return ndimage.convolve(
        skel.astype(np.uint8, copy=False),
        NEIGHBORHOOD,
        mode="constant",
        cval=0,
        output=np.uint8,
    )


def endpoint_and_branch_masks(
    skeleton: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return endpoint, branch-signal, and 26-neighbor-count arrays.

    Branch voxels are intentionally described as a *signal*: adjacent voxels
    around a junction can all have more than two neighbors and should later be
    consolidated by the graph layer rather than interpreted as separate nodes.
    """

    skel = _as_bool_3d(skeleton, "skeleton")
    counts = skeleton_neighbor_counts(skel)
    return skel & (counts == 1), skel & (counts > 2), counts


def _bounded_coordinates(mask: np.ndarray, limit: int) -> tuple[list[list[int]], int]:
    count = int(np.count_nonzero(mask))
    if count == 0 or limit <= 0:
        return [], count
    flat = np.flatnonzero(mask)
    if flat.size > limit:
        # Deterministic even sampling retains coverage without huge JSON output.
        indices = np.linspace(0, flat.size - 1, limit, dtype=np.int64)
        flat = flat[indices]
    coords = np.column_stack(np.unravel_index(flat, mask.shape))
    return coords.astype(int, copy=False).tolist(), count


def _spacing_tuple(spacing: float | Sequence[float] | None) -> tuple[float, float, float]:
    if spacing is None:
        return (1.0, 1.0, 1.0)
    if np.isscalar(spacing):
        value = float(spacing)
        result = (value, value, value)
    else:
        result = tuple(float(value) for value in spacing)
        if len(result) != 3:
            raise ValueError("spacing must be a scalar or three values in z, y, x order")
    if not all(np.isfinite(value) and value > 0 for value in result):
        raise ValueError("spacing values must be positive and finite")
    return result


def extract_skan_graph(
    skeleton: np.ndarray,
    *,
    spacing: float | Sequence[float] | None = None,
    max_branches: int = 10_000,
    max_polyline_points: int = 128,
) -> dict[str, Any]:
    """Extract compact branch records with skan, if it is installed.

    The returned object is always JSON serializable.  A missing or incompatible
    optional skan installation is reported in the object instead of preventing
    connectivity metrics and the dashboard from loading.
    """

    if max_branches < 0 or max_polyline_points < 2:
        raise ValueError("max_branches must be nonnegative; max_polyline_points >= 2")
    skel = _as_bool_3d(skeleton, "skeleton")
    try:
        from skan import Skeleton, summarize
    except (ImportError, ModuleNotFoundError) as exc:
        return {
            "backend": "unavailable",
            "available": False,
            "reason": f"skan is not installed ({exc})",
            "branch_count": None,
            "branches": [],
            "truncated": False,
        }

    try:
        graph = Skeleton(skel, spacing=_spacing_tuple(spacing))
        table = summarize(graph, separator="_")
        branch_count = int(len(table))
        keep = min(branch_count, max_branches)
        branches: list[dict[str, Any]] = []
        for path_id in range(keep):
            row = table.iloc[path_id]
            coords = np.asarray(graph.path_coordinates(path_id))
            if len(coords) > max_polyline_points:
                sample = np.linspace(
                    0, len(coords) - 1, max_polyline_points, dtype=np.int64
                )
                coords = coords[sample]

            def value(*names: str, default: Any = None) -> Any:
                for name in names:
                    if name in row.index:
                        scalar = row[name]
                        return scalar.item() if hasattr(scalar, "item") else scalar
                return default

            branches.append(
                {
                    "id": path_id,
                    "node_a": int(value("node_id_src", "node_id_src", default=-1)),
                    "node_b": int(value("node_id_dst", "node_id_dst", default=-1)),
                    "length": float(value("branch_distance", default=0.0)),
                    "branch_type": int(value("branch_type", default=-1)),
                    # Skan and NumPy use z, y, x array-coordinate order.
                    "polyline_zyx": coords.astype(float, copy=False).tolist(),
                }
            )
        return {
            "backend": "skan",
            "available": True,
            "branch_count": branch_count,
            "branches": branches,
            "truncated": keep < branch_count,
        }
    except Exception as exc:  # optional dependency must fail soft at runtime
        return {
            "backend": "error",
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "branch_count": None,
            "branches": [],
            "truncated": False,
        }


def analyze_skeleton(
    skeleton: np.ndarray,
    *,
    spacing: float | Sequence[float] | None = None,
    coordinate_limit: int = 2_000,
    include_graph: bool = True,
    max_branches: int = 10_000,
    max_polyline_points: int = 128,
) -> dict[str, Any]:
    """Return compact, JSON-safe topology metrics for a skeleton array.

    Full component labels are intentionally excluded; downstream classifiers
    can obtain those with :func:`label_skeleton_components`.
    """

    if coordinate_limit < 0:
        raise ValueError("coordinate_limit must be nonnegative")
    skel = _as_bool_3d(skeleton, "skeleton")
    labels, component_count = label_skeleton_components(skel)
    component_sizes = np.bincount(labels.ravel())[1:]
    main_component = int(np.argmax(component_sizes) + 1) if component_sizes.size else None
    endpoints, branches, _ = endpoint_and_branch_masks(skel)
    endpoint_coords, endpoint_count = _bounded_coordinates(endpoints, coordinate_limit)
    branch_coords, branch_count = _bounded_coordinates(branches, coordinate_limit)

    components = [
        {
            "id": int(index + 1),
            "voxel_count": int(size),
            "is_main": bool(index + 1 == main_component),
        }
        for index, size in enumerate(component_sizes)
    ]
    # A pathological noisy scan could itself have a huge component list.
    components.sort(key=lambda item: item["voxel_count"], reverse=True)
    components_truncated = len(components) > 1_000
    components = components[:1_000]

    result: dict[str, Any] = {
        "skeleton_voxels": int(np.count_nonzero(skel)),
        "connectivity": 26,
        "component_count": component_count,
        "disconnected_region_count": max(0, component_count - 1),
        "main_component_id": main_component,
        "components": components,
        "components_truncated": components_truncated,
        "endpoint_count": endpoint_count,
        "endpoint_coordinates_zyx": endpoint_coords,
        "endpoint_coordinates_truncated": endpoint_count > len(endpoint_coords),
        "branch_voxel_count": branch_count,
        "branch_coordinates_zyx": branch_coords,
        "branch_coordinates_truncated": branch_count > len(branch_coords),
    }
    if include_graph:
        result["graph"] = extract_skan_graph(
            skel,
            spacing=spacing,
            max_branches=max_branches,
            max_polyline_points=max_polyline_points,
        )
    return result


def build_skeleton_analysis(
    mask: np.ndarray,
    **analysis_options: Any,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Skeletonize a mask once and return it with its compact analysis."""

    centerline = skeletonize_mask(mask)
    return centerline, analyze_skeleton(centerline, **analysis_options)
