"""Interactive 3D comparison of a CT lattice scan and its registered design."""

from __future__ import annotations

import argparse
import math
import sys
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html
from plotly.subplots import make_subplots
from scipy import ndimage
from skimage import measure

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (str(REPO_ROOT), str(SRC_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.datasets import DATASETS, get_dataset  # noqa: E402
from lattice_pipeline.cache import ensure_analysis, load_cached_arrays  # noqa: E402
from lattice_pipeline.io import load_volume  # noqa: E402


STATUS_ORDER = ("healthy", "thick", "thin", "missing", "uncertain")
FILTER_ORDER = ("missing", "uncertain", "thin", "thick", "healthy")
STATUS_COLORS = {
    "healthy": "#7f9aa8",
    "missing": "#ff4868",
    "uncertain": "#4da3ff",
    "thin": "#ffb547",
    "thick": "#a978ff",
}
STATUS_LABELS = {
    "healthy": "Healthy",
    "missing": "Missing",
    "uncertain": "Boundary / uncertain",
    "thin": "Thin",
    "thick": "Thick",
}
AXIS_ORDERS = ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")

_MAX_CACHED_ANALYSES = 8
_ANALYSES: OrderedDict[
    tuple[str, float, float | None],
    dict[str, Any],
] = OrderedDict()
_ANALYSIS_LOCK = RLock()


def _analysis(
    dataset_key: str,
    voxel_size: float,
    threshold: float | None = None,
) -> dict[str, Any]:
    threshold_key = None if threshold is None else round(float(threshold), 12)
    key = (dataset_key, round(float(voxel_size), 9), threshold_key)
    with _ANALYSIS_LOCK:
        cached = _ANALYSES.get(key)
        if cached is not None:
            _ANALYSES.move_to_end(key)
            return cached

        analysis = ensure_analysis(
            dataset_key,
            get_dataset(dataset_key),
            threshold=threshold,
            voxel_size_mm=float(voxel_size),
        )
        # Processed mask files hold the most recently computed threshold. Keep
        # the corresponding browser-sized mesh with the analysis so switching
        # back to any recent threshold never reads a mismatched mask or repeats
        # the expensive pipeline.
        analysis["_display_geometry"] = _display_geometry(
            dataset_key,
            str(analysis["meta"]["cache_fingerprint"]),
        )
        _ANALYSES[key] = analysis
        _ANALYSES.move_to_end(key)
        while len(_ANALYSES) > _MAX_CACHED_ANALYSES:
            _ANALYSES.popitem(last=False)
        return analysis


def _axis_indices(axis_order: str) -> tuple[int, int, int]:
    normalized = str(axis_order).upper()
    if normalized not in AXIS_ORDERS:
        raise ValueError(
            f"Unknown axis order {axis_order!r}; choose from {', '.join(AXIS_ORDERS)}"
        )
    source_indices = {"X": 0, "Y": 1, "Z": 2}
    return tuple(source_indices[axis] for axis in normalized)


def _reorder_xyz(points_xyz: Any, axis_order: str) -> np.ndarray:
    """Map public xyz coordinates onto the selected display-axis order."""

    points = np.asarray(points_xyz, dtype=float)
    if points.shape[-1:] != (3,):
        raise ValueError(f"Expected xyz coordinates, got shape {points.shape!r}")
    return points[..., list(_axis_indices(axis_order))]


def _format_xyz(point_xyz: Any) -> str:
    """Format one public XYZ voxel coordinate for the inspection UI."""

    point = np.asarray(point_xyz, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError(f"Expected one finite xyz coordinate, got {point_xyz!r}")
    return f"({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f})"


def _rule_strength(record: dict[str, Any]) -> float | None:
    """Return a non-healthy rule score, including legacy cache compatibility."""

    if record.get("status") == "healthy":
        return None
    value = record.get("rule_strength")
    if value is None:
        value = record.get("confidence")
    if value is None:
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _rule_strength_text(record: dict[str, Any]) -> str:
    value = _rule_strength(record)
    if value is None:
        return "no defect rule triggered"
    return f"rule strength {value:.2f}"


def _strut_geometry(record: dict[str, Any]) -> dict[str, Any]:
    """Derive inspectable geometry from a strut's XYZ polyline."""

    points = np.asarray(record["polyline"], dtype=float)
    if (
        points.ndim != 2
        or points.shape[1:] != (3,)
        or len(points) < 2
        or not np.all(np.isfinite(points))
    ):
        raise ValueError(
            f"Strut {record.get('id', 'unknown')} has invalid polyline coordinates"
        )

    segment_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    length = float(segment_lengths.sum())
    if length <= 1e-12:
        midpoint = points[0].copy()
    else:
        half_length = length / 2.0
        cumulative = np.cumsum(segment_lengths)
        segment_index = int(np.searchsorted(cumulative, half_length, side="left"))
        distance_before = (
            0.0 if segment_index == 0 else float(cumulative[segment_index - 1])
        )
        segment_length = float(segment_lengths[segment_index])
        fraction = (
            0.0
            if segment_length <= 1e-12
            else (half_length - distance_before) / segment_length
        )
        midpoint = (
            points[segment_index]
            + fraction * (points[segment_index + 1] - points[segment_index])
        )

    return {
        "start": points[0],
        "end": points[-1],
        "midpoint": midpoint,
        "length": length,
    }


def _display_axis_ranges(
    axis_order: str,
    axis_maxima: dict[str, float | None] | None,
) -> tuple[list[float] | None, list[float] | None, list[float] | None]:
    """Return Plotly ranges in display order from semantic X/Y/Z maxima."""

    normalized = str(axis_order).upper()
    _axis_indices(normalized)
    maxima = axis_maxima or {}
    ranges: list[list[float] | None] = []
    for axis in normalized:
        raw_maximum = maxima.get(axis)
        if raw_maximum is None:
            ranges.append(None)
            continue
        maximum = float(raw_maximum)
        if not math.isfinite(maximum) or maximum <= 0:
            raise ValueError(f"{axis}-axis maximum must be greater than zero")
        ranges.append([0.0, maximum])
    return ranges[0], ranges[1], ranges[2]


def _axis_upper_bounds(
    axis_maxima: dict[str, float | None] | None,
) -> np.ndarray:
    """Validate semantic XYZ maxima and return an upper-bound vector."""

    ranges = _display_axis_ranges("XYZ", axis_maxima)
    return np.asarray(
        [math.inf if axis_range is None else axis_range[1] for axis_range in ranges],
        dtype=float,
    )


def _record_intersects_bounds(
    record: dict[str, Any],
    kind: str,
    upper: np.ndarray,
) -> bool:
    """Return whether a node or strut intersects an XYZ upper-bound vector."""

    if kind not in {"node", "strut"}:
        raise ValueError(f"Unknown lattice element kind {kind!r}")
    lower = np.where(np.isfinite(upper), 0.0, -math.inf)

    if kind == "node":
        point = np.asarray([record["x"], record["y"], record["z"]], dtype=float)
        return bool(np.all(point >= lower) and np.all(point <= upper))

    points = np.asarray(record["polyline"], dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
        raise ValueError(
            f"Strut {record.get('id', 'unknown')} has invalid polyline coordinates"
        )
    if len(points) == 1:
        return bool(np.all(points[0] >= lower) and np.all(points[0] <= upper))

    # Slab intersection counts a strut whenever any displayed portion of one of
    # its polyline segments falls inside the [0, maximum] XYZ box.
    for start, end in zip(points[:-1], points[1:]):
        direction = end - start
        segment_min = 0.0
        segment_max = 1.0
        for coordinate, delta, minimum, maximum in zip(
            start,
            direction,
            lower,
            upper,
        ):
            if abs(delta) < 1e-12:
                if coordinate < minimum or coordinate > maximum:
                    break
                continue
            enter = (minimum - coordinate) / delta
            leave = (maximum - coordinate) / delta
            if enter > leave:
                enter, leave = leave, enter
            segment_min = max(segment_min, enter)
            segment_max = min(segment_max, leave)
            if segment_min > segment_max:
                break
        else:
            return True
    return False


def _record_intersects_axis_limits(
    record: dict[str, Any],
    kind: str,
    axis_maxima: dict[str, float | None] | None,
) -> bool:
    """Return whether a node or strut intersects the displayed XYZ bounds."""

    return _record_intersects_bounds(
        record,
        kind,
        _axis_upper_bounds(axis_maxima),
    )


def _empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        showarrow=False,
        font={"color": "#9fb3bf", "size": 15},
    )
    figure.update_layout(
        height=760,
        paper_bgcolor="#071018",
        plot_bgcolor="#071018",
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        xaxis={"visible": False},
        yaxis={"visible": False},
    )
    return figure


@lru_cache(maxsize=8)
def _display_geometry(
    dataset_key: str,
    cache_fingerprint: str,
) -> dict[str, np.ndarray]:
    """Build a browser-sized surface from the cached CT segmentation."""

    # cache_fingerprint is intentionally part of the cache key: the mask changes
    # whenever a user applies a different segmentation threshold.
    del cache_fingerprint
    config = get_dataset(dataset_key)
    mask, _ = load_cached_arrays(config)
    stride = int(config["analysis_stride"])
    positions = np.argwhere(mask)
    minimum = positions.min(axis=0)
    maximum = positions.max(axis=0) + 1
    crop = np.asarray(mask[tuple(slice(a, b) for a, b in zip(minimum, maximum))])

    # A coarse translucent surface supplies CT context without overwhelming the
    # registered design graph or shipping the full ~1 GiB volume to the browser.
    surface_step = max(1, math.ceil(max(crop.shape) / 45))
    surface = crop[::surface_step, ::surface_step, ::surface_step]
    vertices_zyx, faces, _, _ = measure.marching_cubes(
        surface.astype(np.uint8), level=0.5
    )
    vertices_zyx = (
        vertices_zyx * (surface_step * stride) + minimum[None, :] * stride
    )
    return {
        "surface_vertices_xyz": vertices_zyx[:, ::-1],
        "surface_faces": faces,
    }


def _strut_trace(
    records: list[dict[str, Any]],
    status: str,
    axis_order: str,
) -> go.Scatter3d:
    x: list[float | None] = []
    y: list[float | None] = []
    z: list[float | None] = []
    customdata: list[list[Any]] = []
    for record in records:
        geometry = _strut_geometry(record)
        element_data = [
            "strut",
            record["id"],
            status,
            _rule_strength_text(record),
            geometry["midpoint"][0],
            geometry["midpoint"][1],
            geometry["midpoint"][2],
            geometry["length"],
            geometry["start"][0],
            geometry["start"][1],
            geometry["start"][2],
            geometry["end"][0],
            geometry["end"][1],
            geometry["end"][2],
        ]
        for point in record["polyline"]:
            display_point = _reorder_xyz(point, axis_order)
            x.append(display_point[0])
            y.append(display_point[1])
            z.append(display_point[2])
            customdata.append(element_data)
        x.append(None)
        y.append(None)
        z.append(None)
        customdata.append(element_data)

    width = {
        "healthy": 2.0,
        "thin": 4.0,
        "thick": 4.2,
        "missing": 5.4,
        "uncertain": 3.0,
    }[status]
    opacity = 0.54 if status == "healthy" else 0.96
    return go.Scatter3d(
        x=x,
        y=y,
        z=z,
        mode="lines",
        line={
            "color": STATUS_COLORS[status],
            "width": width,
            "dash": (
                "dot"
                if status == "missing"
                else "dash" if status == "uncertain" else "solid"
            ),
        },
        opacity=opacity,
        customdata=customdata,
        hovertemplate=(
            f"<b>{STATUS_LABELS[status]} strut</b>"
            "<br>ID %{customdata[1]}"
            "<br>midpoint XYZ (%{customdata[4]:.2f}, %{customdata[5]:.2f}, "
            "%{customdata[6]:.2f}) voxels"
            "<br>start XYZ (%{customdata[8]:.2f}, %{customdata[9]:.2f}, "
            "%{customdata[10]:.2f})"
            "<br>end XYZ (%{customdata[11]:.2f}, %{customdata[12]:.2f}, "
            "%{customdata[13]:.2f})"
            "<br>length %{customdata[7]:.2f} voxels"
            "<br>%{customdata[3]}<extra></extra>"
        ),
        name=f"{STATUS_LABELS[status]} struts",
        showlegend=False,
    )


def _node_trace(
    records: list[dict[str, Any]],
    status: str,
    axis_order: str,
) -> go.Scatter3d:
    missing = status == "missing"
    positions = _reorder_xyz(
        [[record["x"], record["y"], record["z"]] for record in records],
        axis_order,
    )
    return go.Scatter3d(
        x=positions[:, 0],
        y=positions[:, 1],
        z=positions[:, 2],
        mode="markers",
        marker={
            "size": 6.5 if missing else 2.2,
            "symbol": "diamond-open" if missing else "circle",
            "color": STATUS_COLORS[status],
            "opacity": 1.0 if missing else 0.48,
            "line": {
                "width": 2 if missing else 0,
                "color": STATUS_COLORS[status],
            },
        },
        customdata=[
            [
                "node",
                record["id"],
                status,
                _rule_strength_text(record),
                record["x"],
                record["y"],
                record["z"],
            ]
            for record in records
        ],
        hovertemplate=(
            f"<b>{STATUS_LABELS[status]} node</b>"
            "<br>ID %{customdata[1]}"
            "<br>XYZ (%{customdata[4]:.2f}, %{customdata[5]:.2f}, "
            "%{customdata[6]:.2f}) voxels"
            "<br>%{customdata[3]}<extra></extra>"
        ),
        name=f"{STATUS_LABELS[status]} nodes",
        showlegend=False,
    )


def _clicked_element(
    analysis: dict[str, Any],
    click_data: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]] | None:
    if not click_data:
        return None
    custom = click_data.get("points", [{}])[0].get("customdata")
    if not custom or len(custom) < 2 or custom[0] not in {"strut", "node"}:
        return None
    kind, identifier = custom[0], str(custom[1])
    collection = analysis["struts"] if kind == "strut" else analysis["nodes"]
    item = next(
        (record for record in collection if str(record["id"]) == identifier),
        None,
    )
    return (kind, item) if item is not None else None


def _selected_element(
    analysis: dict[str, Any],
    reference: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]] | None:
    """Resolve a compact browser selection against the current analysis."""

    if not reference or reference.get("kind") not in {"strut", "node"}:
        return None
    kind = str(reference["kind"])
    collection = analysis["struts"] if kind == "strut" else analysis["nodes"]
    identifier = str(reference.get("id", ""))
    item = next(
        (record for record in collection if str(record["id"]) == identifier),
        None,
    )
    return (kind, item) if item is not None else None


def _nearest_element(
    analysis: dict[str, Any],
    kind: str,
    position_xyz: Any,
) -> tuple[tuple[str, dict[str, Any]], float]:
    """Return the requested element nearest an XYZ voxel position."""

    point = np.asarray(position_xyz, dtype=float)
    if point.shape != (3,) or not np.all(np.isfinite(point)):
        raise ValueError("Position must contain three finite XYZ voxel coordinates.")
    if kind == "node":
        records = analysis["nodes"]
        if not records:
            raise ValueError("This analysis contains no nodes.")
        positions = np.asarray(
            [[record["x"], record["y"], record["z"]] for record in records],
            dtype=float,
        )
        distances = np.linalg.norm(positions - point[None, :], axis=1)
    elif kind == "strut":
        records = analysis["struts"]
        if not records:
            raise ValueError("This analysis contains no struts.")
        distances = []
        for record in records:
            polyline = np.asarray(record["polyline"], dtype=float)
            best = math.inf
            for start, end in zip(polyline[:-1], polyline[1:]):
                direction = end - start
                denominator = float(np.dot(direction, direction))
                fraction = (
                    0.0
                    if denominator <= 1e-12
                    else float(np.clip(np.dot(point - start, direction) / denominator, 0, 1))
                )
                best = min(best, float(np.linalg.norm(point - (start + fraction * direction))))
            distances.append(best)
        distances = np.asarray(distances, dtype=float)
    else:
        raise ValueError("Element type must be 'strut' or 'node'.")

    index = int(np.argmin(distances))
    return (kind, records[index]), float(distances[index])


def _element_by_id(
    analysis: dict[str, Any],
    kind: str,
    identifier: Any,
) -> tuple[str, dict[str, Any]]:
    """Resolve an exact node or strut ID with a user-facing error."""

    text = str(identifier).strip()
    if not text:
        raise ValueError("Enter an element ID or all three XYZ coordinates.")
    collection = analysis["struts"] if kind == "strut" else analysis["nodes"]
    item = next((record for record in collection if str(record["id"]) == text), None)
    if item is None:
        raise ValueError(f"No {kind} with ID {text} exists in this dataset.")
    return kind, item


def _evidence_focus(
    analysis: dict[str, Any],
    selected: tuple[str, dict[str, Any]],
) -> np.ndarray:
    """Choose the detector's evidence location, falling back to element geometry."""

    kind, item = selected
    defect = next(
        (
            record
            for record in analysis.get("defects", [])
            if record.get("affected_element", {}).get("kind") == kind
            and str(record.get("affected_element", {}).get("id")) == str(item["id"])
        ),
        None,
    )
    if defect is not None:
        location = np.asarray(defect.get("location_voxel"), dtype=float)
        if location.shape == (3,) and np.all(np.isfinite(location)):
            return location
    if kind == "strut":
        return np.asarray(_strut_geometry(item)["midpoint"], dtype=float)
    return np.asarray([item["x"], item["y"], item["z"]], dtype=float)


@lru_cache(maxsize=2)
def _raw_volume(dataset_key: str) -> np.ndarray:
    """Memory-map a source CT volume for responsive evidence slices."""

    return load_volume(get_dataset(dataset_key)["volume"], mmap=True)


def _polyline_plane_intersections(
    points_xyz: np.ndarray,
    *,
    fixed_axis: int,
    fixed_value: float,
    horizontal_axis: int,
    vertical_axis: int,
) -> np.ndarray:
    """Return where a 3D polyline intersects one fixed orthogonal slice."""

    intersections: list[np.ndarray] = []
    tolerance = 1e-8
    for start, end in zip(points_xyz[:-1], points_xyz[1:]):
        start_value = float(start[fixed_axis])
        end_value = float(end[fixed_axis])
        delta = end_value - start_value
        if abs(delta) <= tolerance:
            if abs(start_value - fixed_value) <= 0.5:
                intersections.extend((start, end))
            continue
        fraction = (fixed_value - start_value) / delta
        if -tolerance <= fraction <= 1.0 + tolerance:
            intersections.append(start + np.clip(fraction, 0.0, 1.0) * (end - start))
    if not intersections:
        return np.empty((0, 2), dtype=float)
    points = np.unique(np.round(np.asarray(intersections), 8), axis=0)
    return points[:, [horizontal_axis, vertical_axis]]


def _strut_cross_section(
    volume: np.ndarray,
    item: dict[str, Any],
    focus_xyz: np.ndarray,
    *,
    radius_voxels: int = 14,
) -> tuple[np.ndarray, np.ndarray]:
    """Resample a raw-CT plane perpendicular to a strut at the focus point."""

    points = np.asarray(item["polyline"], dtype=float)
    best_direction: np.ndarray | None = None
    best_distance = math.inf
    for start, end in zip(points[:-1], points[1:]):
        direction = end - start
        denominator = float(np.dot(direction, direction))
        if denominator <= 1e-12:
            continue
        fraction = float(
            np.clip(np.dot(focus_xyz - start, direction) / denominator, 0, 1)
        )
        closest = start + fraction * direction
        distance = float(np.linalg.norm(focus_xyz - closest))
        if distance < best_distance:
            best_distance = distance
            best_direction = direction
    if best_direction is None:
        raise ValueError(f"Strut {item.get('id', 'unknown')} has no usable segment")

    direction = best_direction / np.linalg.norm(best_direction)
    reference = np.zeros(3, dtype=float)
    reference[int(np.argmin(np.abs(direction)))] = 1.0
    basis_u = np.cross(direction, reference)
    basis_u /= np.linalg.norm(basis_u)
    basis_v = np.cross(direction, basis_u)
    basis_v /= np.linalg.norm(basis_v)

    offsets = np.arange(-radius_voxels, radius_voxels + 1, dtype=float)
    grid_u, grid_v = np.meshgrid(offsets, offsets)
    sample_xyz = (
        focus_xyz[None, None, :]
        + grid_u[..., None] * basis_u
        + grid_v[..., None] * basis_v
    )
    image = ndimage.map_coordinates(
        volume,
        [
            sample_xyz[..., 2],
            sample_xyz[..., 1],
            sample_xyz[..., 0],
        ],
        order=1,
        mode="constant",
        cval=np.nan,
        prefilter=False,
    )
    return np.asarray(image), offsets


def _diameter_circle(radius_voxels: float) -> tuple[np.ndarray, np.ndarray]:
    angles = np.linspace(0.0, 2.0 * np.pi, 181)
    return radius_voxels * np.cos(angles), radius_voxels * np.sin(angles)


def _evidence_figure(
    dataset_key: str,
    analysis: dict[str, Any],
    selected: tuple[str, dict[str, Any]] | None,
) -> go.Figure:
    """Build full-resolution orthogonal raw-CT evidence for one element."""

    if selected is None:
        figure = _empty_figure(
            "Enter an ID or XYZ position, or click an element in the 3D view."
        )
        figure.update_layout(height=500)
        return figure

    volume = _raw_volume(dataset_key)
    kind, item = selected
    focus = _evidence_focus(analysis, selected)
    shape_xyz = np.asarray(volume.shape[::-1], dtype=int)
    focus_index = np.clip(np.rint(focus).astype(int), 0, shape_xyz - 1)

    if kind == "strut":
        expected = np.asarray(item["polyline"], dtype=float)
        radius = int(
            np.clip(
                max(30.0, np.max(np.ptp(expected, axis=0)) / 2.0 + 10.0),
                30,
                72,
            )
        )
        element_title = f"Strut {item['id']}"
    else:
        expected = np.asarray([[item["x"], item["y"], item["z"]]], dtype=float)
        radius = 30
        element_title = f"Node {item['id']}"

    def bounds(center: int, maximum: int) -> tuple[int, int]:
        return max(0, center - radius), min(maximum, center + radius + 1)

    x0, x1 = bounds(int(focus_index[0]), int(shape_xyz[0]))
    y0, y1 = bounds(int(focus_index[1]), int(shape_xyz[1]))
    z0, z1 = bounds(int(focus_index[2]), int(shape_xyz[2]))
    x_values = np.arange(x0, x1)
    y_values = np.arange(y0, y1)
    z_values = np.arange(z0, z1)
    xy = np.asarray(volume[int(focus_index[2]), y0:y1, x0:x1])
    xz = np.asarray(volume[z0:z1, int(focus_index[1]), x0:x1])
    yz = np.asarray(volume[z0:z1, y0:y1, int(focus_index[0])])
    panels = (
        (
            "XY",
            xy,
            x_values,
            y_values,
            expected[:, 0],
            expected[:, 1],
            2,
            float(focus_index[2]),
            0,
            1,
        ),
        (
            "XZ",
            xz,
            x_values,
            z_values,
            expected[:, 0],
            expected[:, 2],
            1,
            float(focus_index[1]),
            0,
            2,
        ),
        (
            "YZ",
            yz,
            y_values,
            z_values,
            expected[:, 1],
            expected[:, 2],
            0,
            float(focus_index[0]),
            1,
            2,
        ),
    )
    cross_section: np.ndarray | None = None
    cross_offsets: np.ndarray | None = None
    if kind == "strut":
        cross_section, cross_offsets = _strut_cross_section(
            volume,
            item,
            focus.astype(float),
        )
    evidence_arrays = [panel[1].ravel() for panel in panels]
    if cross_section is not None:
        evidence_arrays.append(cross_section.ravel())
    sampled = np.concatenate(evidence_arrays)
    finite = sampled[np.isfinite(sampled)]
    zmin, zmax = (
        (float(np.percentile(finite, 1)), float(np.percentile(finite, 99.5)))
        if finite.size
        else (0.0, 1.0)
    )
    if zmax <= zmin:
        zmax = zmin + 1.0

    slice_text: tuple[str, ...] = (
        f"XY · Z={focus_index[2]}",
        f"XZ · Y={focus_index[1]}",
        f"YZ · X={focus_index[0]}",
    )
    if cross_section is not None:
        slice_text += ("Perpendicular to strut · diameter review",)
    figure = make_subplots(
        rows=1,
        cols=len(slice_text),
        subplot_titles=slice_text,
        horizontal_spacing=0.035,
    )
    threshold = float(analysis["meta"]["threshold"])
    for column, (
        _plane,
        image,
        horizontal,
        vertical,
        line_x,
        line_y,
        fixed_axis,
        fixed_value,
        horizontal_axis,
        vertical_axis,
    ) in enumerate(
        panels,
        start=1,
    ):
        figure.add_trace(
            go.Heatmap(
                z=image,
                x=horizontal,
                y=vertical,
                coloraxis="coloraxis",
                hovertemplate=(
                    "horizontal %{x}<br>vertical %{y}<br>raw intensity %{z}<extra></extra>"
                ),
            ),
            row=1,
            col=column,
        )
        figure.add_trace(
            go.Contour(
                z=image,
                x=horizontal,
                y=vertical,
                contours={
                    "start": threshold,
                    "end": threshold,
                    "size": max(abs(threshold), 1.0),
                    "coloring": "lines",
                },
                line={"color": "#55d6be", "width": 1.4},
                showscale=False,
                hoverinfo="skip",
                name="active threshold",
                showlegend=column == 1,
            ),
            row=1,
            col=column,
        )
        figure.add_trace(
            go.Scatter(
                x=line_x,
                y=line_y,
                mode="lines+markers" if kind == "strut" else "markers",
                line={"color": "#ff4868", "width": 3, "dash": "dash"},
                marker={
                    "color": "#ff4868",
                    "size": 9 if kind == "node" else 5,
                    "symbol": "x",
                },
                name="expected geometry",
                showlegend=column == 1,
                hovertemplate="expected XYZ projection<extra></extra>",
            ),
            row=1,
            col=column,
        )
        intersections = _polyline_plane_intersections(
            expected,
            fixed_axis=fixed_axis,
            fixed_value=fixed_value,
            horizontal_axis=horizontal_axis,
            vertical_axis=vertical_axis,
        )
        figure.add_trace(
            go.Scatter(
                x=intersections[:, 0],
                y=intersections[:, 1],
                mode="markers",
                marker={
                    "color": "#ffb547",
                    "size": 10,
                    "symbol": "diamond-open",
                    "line": {"width": 2},
                },
                name="expected slice intersection",
                showlegend=column == 1,
                hovertemplate="expected geometry intersects this slice<extra></extra>",
            ),
            row=1,
            col=column,
        )
        focus_horizontal = focus_index[0] if column < 3 else focus_index[1]
        focus_vertical = focus_index[1] if column == 1 else focus_index[2]
        figure.add_trace(
            go.Scatter(
                x=[focus_horizontal],
                y=[focus_vertical],
                mode="markers",
                marker={
                    "color": "#ffffff",
                    "size": 11,
                    "symbol": "circle-open",
                    "line": {"width": 2},
                },
                name="inspection point",
                showlegend=column == 1,
                hoverinfo="skip",
            ),
            row=1,
            col=column,
        )
        figure.update_xaxes(
            title_text=panels[column - 1][0][0 if column < 3 else 1],
            range=[float(horizontal[0]), float(horizontal[-1])],
            row=1,
            col=column,
        )
        figure.update_yaxes(
            title_text=panels[column - 1][0][1],
            range=[float(vertical[0]), float(vertical[-1])],
            scaleanchor=f"x{column if column > 1 else ''}",
            scaleratio=1,
            row=1,
            col=column,
        )

    if cross_section is not None and cross_offsets is not None:
        cross_column = 4
        figure.add_trace(
            go.Heatmap(
                z=cross_section,
                x=cross_offsets,
                y=cross_offsets,
                coloraxis="coloraxis",
                hovertemplate=(
                    "cross-section u %{x:.1f}<br>v %{y:.1f}"
                    "<br>raw intensity %{z:.1f}<extra></extra>"
                ),
            ),
            row=1,
            col=cross_column,
        )
        figure.add_trace(
            go.Contour(
                z=cross_section,
                x=cross_offsets,
                y=cross_offsets,
                contours={
                    "start": threshold,
                    "end": threshold,
                    "size": max(abs(threshold), 1.0),
                    "coloring": "lines",
                },
                line={"color": "#55d6be", "width": 1.4},
                showscale=False,
                hoverinfo="skip",
                name="active threshold",
                showlegend=False,
            ),
            row=1,
            col=cross_column,
        )
        voxel_size_um = float(analysis["meta"]["voxel_size_mm"]) * 1000.0
        design_um = item.get("design_thickness_um")
        measured_um = item.get("measured_thickness_um")
        for diameter_um, color, label, dash in (
            (design_um, "#ff4868", "expected diameter", "dash"),
            (measured_um, "#a978ff", "detector diameter estimate", "dot"),
        ):
            if diameter_um is None or voxel_size_um <= 0:
                continue
            circle_x, circle_y = _diameter_circle(
                float(diameter_um) / (2.0 * voxel_size_um)
            )
            figure.add_trace(
                go.Scatter(
                    x=circle_x,
                    y=circle_y,
                    mode="lines",
                    line={"color": color, "width": 2, "dash": dash},
                    name=label,
                    showlegend=True,
                    hovertemplate=(
                        f"{label}: {float(diameter_um):.0f} μm<extra></extra>"
                    ),
                ),
                row=1,
                col=cross_column,
            )
        figure.add_trace(
            go.Scatter(
                x=[0.0],
                y=[0.0],
                mode="markers",
                marker={
                    "color": "#ffffff",
                    "size": 10,
                    "symbol": "circle-open",
                    "line": {"width": 2},
                },
                name="inspection point",
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1,
            col=cross_column,
        )
        figure.update_xaxes(
            title_text="cross-section u (voxels)",
            range=[float(cross_offsets[0]), float(cross_offsets[-1])],
            row=1,
            col=cross_column,
        )
        figure.update_yaxes(
            title_text="cross-section v (voxels)",
            range=[float(cross_offsets[0]), float(cross_offsets[-1])],
            scaleanchor="x4",
            scaleratio=1,
            row=1,
            col=cross_column,
        )

    figure.update_layout(
        height=540,
        title={
            "text": (
                f"{element_title} · raw CT evidence at "
                f"XYZ {_format_xyz(focus_index)}"
            ),
            "x": 0.02,
            "font": {"size": 16, "color": "#edf5f8"},
        },
        paper_bgcolor="#071018",
        plot_bgcolor="#071018",
        font={"color": "#9fb3bf"},
        margin={"l": 58, "r": 28, "t": 82, "b": 60},
        coloraxis={
            "colorscale": "Gray",
            "cmin": zmin,
            "cmax": zmax,
            "colorbar": {
                "title": "raw",
                "thickness": 9,
                "len": 0.72,
                "x": 1.015,
            },
        },
        legend={
            "orientation": "h",
            "x": 0,
            "y": -0.16,
            "font": {"size": 10},
        },
        uirevision=(
            f"evidence:{dataset_key}:{analysis['meta']['cache_fingerprint']}:"
            f"{kind}:{item['id']}"
        ),
    )
    return figure


def _evidence_details(
    analysis: dict[str, Any],
    selected: tuple[str, dict[str, Any]] | None,
) -> list[Any]:
    """Describe the detector result without overstating visual verification."""

    if selected is None:
        return [
            html.Span(
                "The red overlay is expected design geometry; cyan is the active "
                "full-resolution threshold contour.",
                className="selection-hint",
            )
        ]
    kind, item = selected
    status = str(item["status"])
    review_label = (
        "Not manually verified" if status == "healthy" else "Needs review"
    )
    details: list[Any] = [
        html.Span(
            f"{STATUS_LABELS.get(status, status.title())} candidate",
            className=f"selection-status status-{status}",
        ),
        html.Strong(f"{kind.title()} ID {item['id']}"),
        html.Span(
            review_label,
            className=(
                "review-status review-neutral"
                if status == "healthy"
                else "review-status review-needed"
            ),
        ),
        html.Span(_rule_strength_text(item)),
    ]
    if kind == "strut":
        details.extend(
            [
                html.Span(
                    f"combined path support "
                    f"{100 * float(item.get('present_fraction', 0)):.1f}%"
                ),
                html.Span(
                    f"mask material "
                    f"{100 * float(item.get('mask_material_fraction', 0)):.1f}%"
                ),
                html.Span(
                    f"skeleton-near "
                    f"{100 * float(item.get('skeleton_support_fraction', 0)):.1f}%"
                ),
            ]
        )
        median_distance = item.get("median_skeleton_distance_vox")
        if median_distance is not None:
            details.append(
                html.Span(
                    f"median skeleton distance {float(median_distance):.2f} "
                    "analysis voxels"
                )
            )
        measured = item.get("measured_thickness_um")
        design = item.get("design_thickness_um")
        ratio = item.get("thickness_ratio")
        if measured is not None:
            details.append(html.Span(f"diameter estimate {float(measured):.0f} μm"))
        if design is not None:
            details.append(html.Span(f"nominal diameter {float(design):.0f} μm"))
        if ratio is not None:
            details.append(html.Span(f"thickness ratio {float(ratio):.2f}×"))
        thresholds = item.get("decision_thresholds", {})
        if status == "missing" and thresholds.get(
            "missing_present_fraction"
        ) is not None:
            details.append(
                html.Span(
                    "missing rule < "
                    f"{100 * float(thresholds['missing_present_fraction']):.1f}% "
                    "path support"
                )
            )
        elif status == "thick" and thresholds.get("thick_ratio") is not None:
            details.append(
                html.Span(
                    f"thick rule > {float(thresholds['thick_ratio']):.2f}×"
                )
            )
        elif status == "thin" and thresholds.get("thin_ratio") is not None:
            details.append(
                html.Span(
                    f"thin rule < {float(thresholds['thin_ratio']):.2f}×"
                )
            )
    else:
        details.extend(
            [
                html.Span(
                    "material at expected voxel: "
                    + ("yes" if item.get("mask_present") else "no")
                ),
                html.Span(
                    "skeleton within rule radius: "
                    + ("yes" if item.get("skeleton_near") else "no")
                ),
            ]
        )
        skeleton_distance = item.get("skeleton_distance_vox")
        if skeleton_distance is not None:
            details.append(
                html.Span(
                    f"skeleton distance {float(skeleton_distance):.2f} "
                    "analysis voxels"
                )
            )
        node_radius = item.get("decision_thresholds", {}).get(
            "node_presence_radius_vox"
        )
        if node_radius is not None:
            details.append(
                html.Span(
                    f"node presence radius {float(node_radius):.2f} "
                    "analysis voxels"
                )
            )
    details.extend(
        [
            html.Span(
                f"threshold {float(analysis['meta']['threshold']):g}",
                className="threshold-readout",
            ),
            html.Span(
                (
                    "The red line is a 3D projection; the gold diamond is where "
                    "the expected geometry intersects each fixed slice. A long "
                    "bright line in one view and a dot in another can be normal "
                    "for an angled strut—the three panels are not independent "
                    "votes. "
                )
                + (
                    "The perpendicular panel supports diameter review, but its "
                    "circles use estimated spacing and one active threshold; "
                    "the purple circle is the coarse path-level detector estimate, "
                    "not a measurement of this single cross-section. "
                    if kind == "strut"
                    else ""
                )
                + "This remains a candidate until the evidence is reviewed.",
                className="evidence-caveat",
            ),
        ]
    )
    return details


def _selection_highlight(
    selected: tuple[str, dict[str, Any]] | None,
    axis_order: str,
) -> go.Scatter3d | None:
    if selected is None:
        return None
    kind, item = selected
    if kind == "strut":
        points = _reorder_xyz(item["polyline"], axis_order)
        return go.Scatter3d(
            x=points[:, 0],
            y=points[:, 1],
            z=points[:, 2],
            mode="lines",
            line={"color": "#ffffff", "width": 9},
            opacity=0.9,
            hoverinfo="skip",
            showlegend=False,
        )
    point = _reorder_xyz([item["x"], item["y"], item["z"]], axis_order)
    return go.Scatter3d(
        x=[point[0]],
        y=[point[1]],
        z=[point[2]],
        mode="markers",
        marker={
            "size": 12,
            "symbol": "diamond-open",
            "color": "#ffffff",
            "line": {"width": 3, "color": "#ffffff"},
        },
        hoverinfo="skip",
        showlegend=False,
    )


def _inspection_figure(
    dataset_key: str,
    analysis: dict[str, Any],
    statuses: list[str],
    elements: list[str],
    show_ct: bool,
    selected: tuple[str, dict[str, Any]] | None,
    axis_order: str = "XYZ",
    axis_maxima: dict[str, float | None] | None = None,
) -> go.Figure:
    allowed = set(statuses or [])
    element_types = set(elements or [])
    figure = go.Figure()
    normalized_axis_order = str(axis_order).upper()
    _axis_indices(normalized_axis_order)
    display_ranges = _display_axis_ranges(normalized_axis_order, axis_maxima)
    axis_upper = _axis_upper_bounds(axis_maxima)
    bounded_struts = (
        [
            record
            for record in analysis["struts"]
            if _record_intersects_bounds(record, "strut", axis_upper)
        ]
        if "struts" in element_types
        else []
    )
    bounded_nodes = (
        [
            record
            for record in analysis["nodes"]
            if _record_intersects_bounds(record, "node", axis_upper)
        ]
        if "nodes" in element_types
        else []
    )

    if show_ct:
        geometry = analysis.get("_display_geometry")
        if geometry is None:
            geometry = _display_geometry(
                dataset_key,
                str(analysis["meta"]["cache_fingerprint"]),
            )
        vertices = _reorder_xyz(
            geometry["surface_vertices_xyz"],
            normalized_axis_order,
        )
        faces = geometry["surface_faces"]
        figure.add_trace(
            go.Mesh3d(
                x=vertices[:, 0],
                y=vertices[:, 1],
                z=vertices[:, 2],
                i=faces[:, 0],
                j=faces[:, 1],
                k=faces[:, 2],
                color="#d6e4ea",
                opacity=0.10,
                flatshading=True,
                hoverinfo="skip",
                name="CT segmentation",
                showlegend=False,
            )
        )

    for status in STATUS_ORDER:
        if status not in allowed:
            continue
        if "struts" in element_types:
            struts = [
                record for record in bounded_struts
                if record["status"] == status
            ]
            if struts:
                figure.add_trace(
                    _strut_trace(struts, status, normalized_axis_order)
                )
        if "nodes" in element_types:
            nodes = [
                record for record in bounded_nodes
                if record["status"] == status
            ]
            if nodes:
                figure.add_trace(
                    _node_trace(nodes, status, normalized_axis_order)
                )

    if selected is not None:
        kind, item = selected
        element_key = "struts" if kind == "strut" else "nodes"
        if (
            item["status"] in allowed
            and element_key in element_types
            and _record_intersects_bounds(item, kind, axis_upper)
        ):
            highlight = _selection_highlight(selected, normalized_axis_order)
            if highlight is not None:
                figure.add_trace(highlight)

    figure.update_layout(
        height=760,
        paper_bgcolor="#071018",
        plot_bgcolor="#071018",
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        hoverlabel={
            "bgcolor": "#10232f",
            "bordercolor": "#35505f",
            "font": {"color": "#f5fbff", "size": 12},
        },
        scene={
            "aspectmode": "data",
            "bgcolor": "#071018",
            "camera": {"eye": {"x": 1.45, "y": 1.45, "z": 1.1}},
            "xaxis": {
                "title": normalized_axis_order[0],
                "color": "#6f8794",
                "gridcolor": "#1b303c",
                "showbackground": False,
                "range": display_ranges[0],
            },
            "yaxis": {
                "title": normalized_axis_order[1],
                "color": "#6f8794",
                "gridcolor": "#1b303c",
                "showbackground": False,
                "range": display_ranges[1],
            },
            "zaxis": {
                "title": (
                    "Z / slice"
                    if normalized_axis_order[2] == "Z"
                    else normalized_axis_order[2]
                ),
                "color": "#6f8794",
                "gridcolor": "#1b303c",
                "showbackground": False,
                "range": display_ranges[2],
            },
        },
        # Keep the user's orbit/zoom while filters update.
        uirevision=(
            f"{dataset_key}:{analysis['meta']['cache_fingerprint']}:"
            f"{normalized_axis_order}:{display_ranges}"
        ),
    )
    return figure


def _visible_summary(
    analysis: dict[str, Any],
    statuses: list[str],
    elements: list[str],
    axis_maxima: dict[str, float | None] | None = None,
) -> list[Any]:
    allowed = set(statuses or [])
    element_types = set(elements or [])
    axis_upper = _axis_upper_bounds(axis_maxima)
    visible_struts = [
        record
        for record in analysis["struts"]
        if _record_intersects_bounds(record, "strut", axis_upper)
    ]
    visible_nodes = [
        record
        for record in analysis["nodes"]
        if _record_intersects_bounds(record, "node", axis_upper)
    ]
    n_struts = (
        sum(record["status"] in allowed for record in visible_struts)
        if "struts" in element_types
        else 0
    )
    n_nodes = (
        sum(record["status"] in allowed for record in visible_nodes)
        if "nodes" in element_types
        else 0
    )
    missing_struts = sum(
        record["status"] == "missing" for record in visible_struts
    )
    missing_nodes = sum(
        record["status"] == "missing" for record in visible_nodes
    )
    summary = [
        html.Span(f"{n_struts:,} struts · {n_nodes:,} nodes visible"),
        html.Span("•", className="summary-dot"),
        html.Span(
            f"{missing_struts:,} missing struts · {missing_nodes:,} missing nodes detected",
            className="missing-summary",
        ),
    ]
    for status in FILTER_ORDER[1:]:
        status_struts = sum(
            record["status"] == status for record in visible_struts
        )
        status_nodes = sum(
            record["status"] == status for record in visible_nodes
        )
        summary.extend(
            [
                html.Span("•", className="summary-dot"),
                html.Span(
                    f"{status_struts:,} {STATUS_LABELS[status].lower()} struts · "
                    f"{status_nodes:,} {STATUS_LABELS[status].lower()} nodes",
                    className=f"status-count status-count-{status}",
                ),
            ]
        )
    flagged_statuses = set(FILTER_ORDER[:-1])
    total_flagged = sum(
        record["status"] in flagged_statuses
        for record in visible_struts
    ) + sum(
        record["status"] in flagged_statuses
        for record in visible_nodes
    )
    summary.extend(
        [
            html.Span("•", className="summary-dot"),
            html.Span(
                f"{total_flagged:,} total flagged elements",
                className="total-flagged-summary",
            ),
        ]
    )
    validation = analysis.get("validation")
    if validation:
        strut_metrics = validation["struts"]
        summary.extend(
            [
                html.Span("•", className="summary-dot"),
                html.Span(
                    f"CAD validation: {strut_metrics['true_positive']}/"
                    f"{strut_metrics['expected']} intentional struts matched · "
                    f"F1 {100 * float(strut_metrics['f1']):.1f}%",
                    className="validation-summary",
                ),
            ]
        )
    return summary


def _selection_details(
    selected: tuple[str, dict[str, Any]] | None,
) -> list[Any]:
    if selected is None:
        return [
            html.Span("Click a strut or node to inspect it.", className="selection-hint"),
            html.Span(
                "Drag to orbit · scroll to zoom · double-click to reset",
                className="interaction-hint",
            ),
        ]

    kind, item = selected
    status = item["status"]
    details: list[Any] = [
        html.Span(
            f"{STATUS_LABELS.get(status, status.title())} {kind}",
            className=f"selection-status status-{status}",
        ),
        html.Strong(f"ID {item['id']}"),
        html.Span(_rule_strength_text(item)),
    ]
    if kind == "strut":
        geometry = _strut_geometry(item)
        details.extend(
            [
                html.Span(f"midpoint XYZ {_format_xyz(geometry['midpoint'])} voxels"),
                html.Span(f"start XYZ {_format_xyz(geometry['start'])}"),
                html.Span(f"end XYZ {_format_xyz(geometry['end'])}"),
                html.Span(f"length {geometry['length']:.2f} voxels"),
            ]
        )
        details.append(
            html.Span(f"present {100 * float(item.get('present_fraction', 0)):.1f}%")
        )
        measured = item.get("measured_thickness_um")
        design = item.get("design_thickness_um")
        if measured is not None:
            details.append(html.Span(f"measured {float(measured):.0f} μm"))
        if design is not None:
            details.append(html.Span(f"design {float(design):.0f} μm"))
        ratio = item.get("thickness_ratio")
        if ratio is not None:
            details.append(html.Span(f"ratio {float(ratio):.2f}×"))
    else:
        details.append(
            html.Span(
                f"XYZ {_format_xyz([item['x'], item['y'], item['z']])} voxels"
            )
        )
        details.append(html.Span(f"design degree {item.get('degree', '—')}"))
    if item.get("boundary_reason"):
        details.append(
            html.Span("scan boundary / registration mismatch")
        )
    return details


def _filter_options() -> list[dict[str, Any]]:
    return [
        {
            "label": html.Span(
                [
                    html.I(
                        className="filter-swatch",
                        style={"backgroundColor": STATUS_COLORS[status]},
                    ),
                    STATUS_LABELS[status],
                ],
                className="filter-label",
            ),
            "value": status,
        }
        for status in FILTER_ORDER
    ]


def create_app(default_dataset: str = "missing_struts") -> Dash:
    app = Dash(__name__, title="Registered Lattice Defect Map")
    config = get_dataset(default_dataset)
    volume_name = Path(config["volume"]).name
    design_name = Path(config["design"]).name

    app.layout = html.Main(
        [
            dcc.Store(id="selected-element"),
            html.Header(
                [
                    html.Div(
                        [
                            html.Div("LLNL DSSI 2026 · CT / DESIGN COMPARISON", className="eyebrow"),
                            html.H1("Registered lattice defect map"),
                            html.P(
                                "Expected JSON geometry classified against the segmented TIFF volume.",
                                className="subtitle",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.B("TIFF"), html.Span(volume_name)],
                                className="source-file",
                            ),
                            html.Div(
                                [html.B("JSON"), html.Span(design_name)],
                                className="source-file",
                            ),
                        ],
                        className="source-files",
                    ),
                ],
                className="model-header",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Span("Status", className="toolbar-label"),
                                    dcc.Checklist(
                                        id="status-filters",
                                        options=_filter_options(),
                                        value=list(FILTER_ORDER),
                                        inline=True,
                                        className="status-filters",
                                    ),
                                ],
                                className="filter-group",
                            ),
                            html.Div(
                                [
                                    html.Span("Elements", className="toolbar-label"),
                                    dcc.Checklist(
                                        id="element-filters",
                                        options=[
                                            {"label": "Struts", "value": "struts"},
                                            {"label": "Nodes", "value": "nodes"},
                                        ],
                                        value=["struts", "nodes"],
                                        inline=True,
                                        className="element-filters",
                                    ),
                                    dcc.Checklist(
                                        id="show-ct",
                                        options=[{"label": "CT surface", "value": "surface"}],
                                        value=["surface"],
                                        inline=True,
                                        className="element-filters ct-toggle",
                                    ),
                                ],
                                className="filter-group secondary-filters",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        "Threshold",
                                        htmlFor="threshold-control",
                                        className="toolbar-label",
                                    ),
                                    html.Div(
                                        [
                                            dcc.Input(
                                                id="threshold-control",
                                                type="number",
                                                value=None,
                                                debounce=True,
                                                placeholder="Auto (Otsu)",
                                                step="any",
                                                className="threshold-input",
                                            ),
                                            html.Button(
                                                "Auto",
                                                id="threshold-auto",
                                                type="button",
                                                className="control-button",
                                                title="Restore automatic Otsu thresholding",
                                            ),
                                        ],
                                        className="threshold-controls",
                                    ),
                                    html.Span(
                                        "Enter a value, then press Enter. Clear for Otsu.",
                                        className="control-help",
                                    ),
                                ],
                                className="parameter-control",
                            ),
                            html.Div(
                                [
                                    html.Span(
                                        "Axis maximum",
                                        className="toolbar-label",
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                [
                                                    html.Span("X"),
                                                    dcc.Input(
                                                        id="x-axis-max",
                                                        type="number",
                                                        value=None,
                                                        debounce=True,
                                                        placeholder="Auto",
                                                        min=0.000001,
                                                        step="any",
                                                        className="axis-limit-input",
                                                    ),
                                                ],
                                                className="axis-limit-field",
                                            ),
                                            html.Label(
                                                [
                                                    html.Span("Y"),
                                                    dcc.Input(
                                                        id="y-axis-max",
                                                        type="number",
                                                        value=None,
                                                        debounce=True,
                                                        placeholder="Auto",
                                                        min=0.000001,
                                                        step="any",
                                                        className="axis-limit-input",
                                                    ),
                                                ],
                                                className="axis-limit-field",
                                            ),
                                            html.Label(
                                                [
                                                    html.Span("Z"),
                                                    dcc.Input(
                                                        id="z-axis-max",
                                                        type="number",
                                                        value=None,
                                                        debounce=True,
                                                        placeholder="Auto",
                                                        min=0.000001,
                                                        step="any",
                                                        className="axis-limit-input",
                                                    ),
                                                ],
                                                className="axis-limit-field",
                                            ),
                                        ],
                                        className="axis-limit-controls",
                                    ),
                                    html.Span(
                                        "Limits the displayed region and defect counts. "
                                        "Clear a value for Auto.",
                                        className="control-help",
                                    ),
                                ],
                                className="parameter-control axis-limit-control",
                            ),
                        ],
                        className="model-toolbar",
                    ),
                    html.Div(
                        [
                            html.Div(
                                id="visible-summary",
                                className="visible-summary-content",
                            ),
                            html.Span(
                                id="threshold-readout",
                                className="threshold-readout",
                            ),
                        ],
                        className="visible-summary",
                    ),
                    dcc.Loading(
                        type="circle",
                        color="#55d6be",
                        children=dcc.Graph(
                            id="viewer",
                            figure=_empty_figure("Preparing registered TIFF / JSON comparison…"),
                            config={
                                "displaylogo": False,
                                "scrollZoom": True,
                                "responsive": True,
                            },
                        ),
                    ),
                    html.Div(id="selection-details", className="selection-details"),
                ],
                className="model-panel",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        "RAW CT CANDIDATE REVIEW",
                                        className="eyebrow",
                                    ),
                                    html.H2("Inspect a node or strut"),
                                    html.P(
                                        "Enter an exact element ID or an XYZ voxel "
                                        "position. Positions resolve to the nearest "
                                        "requested graph element. Detector labels are "
                                        "candidates, not verified conclusions.",
                                        className="verification-copy",
                                    ),
                                ],
                                className="verification-heading",
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        [
                                            html.Span(
                                                "Element",
                                                className="toolbar-label",
                                            ),
                                            dcc.Dropdown(
                                                id="lookup-kind",
                                                options=[
                                                    {
                                                        "label": "Strut",
                                                        "value": "strut",
                                                    },
                                                    {
                                                        "label": "Node",
                                                        "value": "node",
                                                    },
                                                ],
                                                value="strut",
                                                clearable=False,
                                                searchable=False,
                                                className="lookup-dropdown",
                                            ),
                                        ],
                                        className="lookup-field lookup-kind",
                                    ),
                                    html.Label(
                                        [
                                            html.Span(
                                                "ID",
                                                className="toolbar-label",
                                            ),
                                            dcc.Input(
                                                id="lookup-id",
                                                type="text",
                                                placeholder="e.g. 1284",
                                                debounce=False,
                                                className="lookup-input lookup-id",
                                            ),
                                        ],
                                        className="lookup-field",
                                    ),
                                    html.Span("or", className="lookup-or"),
                                    *[
                                        html.Label(
                                            [
                                                html.Span(
                                                    axis,
                                                    className="toolbar-label",
                                                ),
                                                dcc.Input(
                                                    id=f"lookup-{axis.lower()}",
                                                    type="number",
                                                    placeholder=axis,
                                                    step="any",
                                                    debounce=False,
                                                    className="lookup-input lookup-coordinate",
                                                ),
                                            ],
                                            className="lookup-field",
                                        )
                                        for axis in "XYZ"
                                    ],
                                    html.Button(
                                        "Generate evidence",
                                        id="inspect-element",
                                        type="button",
                                        className="inspect-button",
                                    ),
                                ],
                                className="lookup-controls",
                            ),
                        ],
                        className="verification-toolbar",
                    ),
                    html.Div(
                        "You can also click a node or strut in the 3D view.",
                        id="lookup-feedback",
                        className="lookup-feedback",
                    ),
                    dcc.Loading(
                        type="circle",
                        color="#55d6be",
                        children=dcc.Graph(
                            id="evidence-view",
                            figure=_evidence_figure(
                                default_dataset,
                                {"meta": {"threshold": 0}},
                                None,
                            ),
                            config={
                                "displaylogo": False,
                                "responsive": True,
                                "toImageButtonOptions": {
                                    "format": "png",
                                    "filename": "lattice_ct_evidence",
                                    "scale": 2,
                                },
                            },
                        ),
                    ),
                    html.Div(
                        id="evidence-details",
                        className="selection-details evidence-details",
                    ),
                ],
                className="model-panel verification-panel",
            ),
        ],
        className="shell",
    )

    @app.callback(
        Output("selected-element", "data"),
        Output("lookup-feedback", "children"),
        Input("viewer", "clickData"),
        Input("inspect-element", "n_clicks"),
        State("lookup-kind", "value"),
        State("lookup-id", "value"),
        State("lookup-x", "value"),
        State("lookup-y", "value"),
        State("lookup-z", "value"),
        State("threshold-control", "value"),
        prevent_initial_call=True,
    )
    def select_element(
        click_data: dict[str, Any] | None,
        _inspect_clicks: int | None,
        kind: str,
        identifier: str | None,
        x: float | None,
        y: float | None,
        z: float | None,
        threshold_value: float | None,
    ) -> tuple[dict[str, Any] | None, Any]:
        try:
            threshold = None if threshold_value is None else float(threshold_value)
            analysis = _analysis(
                default_dataset,
                float(config["voxel_size_mm"]),
                threshold,
            )
            if ctx.triggered_id == "viewer":
                selected = _clicked_element(analysis, click_data)
                if selected is None:
                    raise ValueError("Click a registered node or strut trace.")
                distance_text = ""
            elif identifier is not None and str(identifier).strip():
                selected = _element_by_id(analysis, kind, identifier)
                distance_text = ""
            else:
                if any(value is None for value in (x, y, z)):
                    raise ValueError(
                        "Enter an element ID or all three XYZ voxel coordinates."
                    )
                selected, distance = _nearest_element(analysis, kind, [x, y, z])
                distance_text = f" · {distance:.2f} voxels from entered position"
            selected_kind, item = selected
            return (
                {"kind": selected_kind, "id": item["id"]},
                html.Span(
                    [
                        html.Strong(
                            f"Selected {selected_kind} ID {item['id']}"
                        ),
                        f"{distance_text}. Generating full-resolution raw CT evidence.",
                    ]
                ),
            )
        except Exception as exc:
            return None, html.Span(str(exc), className="error-message")

    @app.callback(
        Output("viewer", "figure"),
        Output("visible-summary", "children"),
        Output("selection-details", "children"),
        Output("threshold-readout", "children"),
        Input("status-filters", "value"),
        Input("element-filters", "value"),
        Input("show-ct", "value"),
        Input("selected-element", "data"),
        Input("threshold-control", "value"),
        Input("x-axis-max", "value"),
        Input("y-axis-max", "value"),
        Input("z-axis-max", "value"),
    )
    def update_model(
        statuses: list[str],
        elements: list[str],
        show_ct: list[str],
        selected_reference: dict[str, Any] | None,
        threshold_value: float | None,
        x_axis_max: float | None,
        y_axis_max: float | None,
        z_axis_max: float | None,
    ) -> tuple[Any, ...]:
        try:
            threshold = (
                None if threshold_value is None else float(threshold_value)
            )
            analysis = _analysis(
                default_dataset,
                float(config["voxel_size_mm"]),
                threshold,
            )
            selected = _selected_element(analysis, selected_reference)
            active_threshold = float(analysis["meta"]["threshold"])
            threshold_source = analysis["meta"]["threshold_source"]
            source_label = (
                "automatic Otsu"
                if threshold_source in {"otsu", "sampled_otsu"}
                else "manual"
            )
            axis_maxima = {
                "X": x_axis_max,
                "Y": y_axis_max,
                "Z": z_axis_max,
            }
            return (
                _inspection_figure(
                    default_dataset,
                    analysis,
                    statuses or [],
                    elements or [],
                    "surface" in (show_ct or []),
                    selected,
                    "XYZ",
                    axis_maxima,
                ),
                _visible_summary(
                    analysis,
                    statuses or [],
                    elements or [],
                    axis_maxima,
                ),
                _selection_details(selected),
                f"Threshold {active_threshold:g} · {source_label}",
            )
        except Exception as exc:
            message = f"Could not load registered comparison: {exc}"
            return (
                _empty_figure(message),
                html.Span(message, className="error-message"),
                [html.Span(message, className="error-message")],
                "Threshold unavailable",
            )

    @app.callback(
        Output("evidence-view", "figure"),
        Output("evidence-details", "children"),
        Input("selected-element", "data"),
        Input("threshold-control", "value"),
    )
    def update_evidence(
        selected_reference: dict[str, Any] | None,
        threshold_value: float | None,
    ) -> tuple[go.Figure, list[Any]]:
        try:
            threshold = None if threshold_value is None else float(threshold_value)
            analysis = _analysis(
                default_dataset,
                float(config["voxel_size_mm"]),
                threshold,
            )
            selected = _selected_element(analysis, selected_reference)
            return (
                _evidence_figure(default_dataset, analysis, selected),
                _evidence_details(analysis, selected),
            )
        except Exception as exc:
            message = f"Could not generate raw CT evidence: {exc}"
            figure = _empty_figure(message)
            figure.update_layout(height=500)
            return figure, [html.Span(message, className="error-message")]

    @app.callback(
        Output("threshold-control", "value"),
        Input("threshold-auto", "n_clicks"),
        prevent_initial_call=True,
    )
    def restore_automatic_threshold(_clicks: int | None) -> None:
        return None

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=DATASETS, default="missing_struts")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--preprocess-only", action="store_true")
    args = parser.parse_args()
    if args.preprocess_only:
        analysis = ensure_analysis(args.dataset, get_dataset(args.dataset))
        print(
            f"Cached {args.dataset}: {len(analysis['defects']):,} candidate defects "
            f"in {analysis['_cache']['directory']}"
        )
        return
    viewer_app = create_app(args.dataset)
    print(f"Registered lattice defect map: http://{args.host}:{args.port}")
    viewer_app.run(host=args.host, port=args.port, debug=False)


app = create_app()
server = app.server

if __name__ == "__main__":
    main()
